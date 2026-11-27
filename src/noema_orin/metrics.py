"""Cohort metrics from session-end log lines (slices S6/S8). Local SQLite, mirrored to D1 by memory_sync.

Each line players.py prints at session end becomes one `sessions` row. Turn lines give the
role-verb rate. Re-running is idempotent: rows are keyed by (log file, line number).
"""

import argparse
import contextlib
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

from .roles import ROLES

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(src TEXT, line INTEGER, ts REAL, member TEXT, role TEXT, actions INTEGER,
  stop_reason TEXT, stop_detail TEXT, role_actions INTEGER, idle_actions INTEGER, turns INTEGER,
  drops INTEGER, rejections TEXT, PRIMARY KEY(src, line));
CREATE TABLE IF NOT EXISTS marks(src TEXT PRIMARY KEY, offset INTEGER);
CREATE TABLE IF NOT EXISTS stuck(src TEXT PRIMARY KEY, zero_energy_streak INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS cost(src TEXT, line INTEGER, ts REAL, calls INTEGER, fallbacks INTEGER, PRIMARY KEY(src, line));
CREATE TABLE IF NOT EXISTS cost_marks(src TEXT PRIMARY KEY, calls_total INTEGER, fallbacks_total INTEGER);
CREATE TABLE IF NOT EXISTS rsi_events(src TEXT, line INTEGER, ts REAL, member TEXT, verdict TEXT, fitness REAL, reason TEXT,
  PRIMARY KEY(src, line));
"""
IDLE = {"LOOK", "WAIT", "INSPECT", "MOVE"}
STUCK_TURNS = 10
DAILY_CALL_CAP = 10_000  # Workers AI daily cap (memory worker /usage)
CAP_ALARM = 0.7  # S15
FALLBACK_ALARM = 0.05  # S15: Ollama fallbacks / calls


def zero_energy_streak(lines: list[str]) -> int:
    """Trailing run of turns logged with budgets.energy == 0 (engine lock, Noema#907)."""
    streak = 0
    for raw in reversed(lines):
        if not raw.startswith('{"turn"'):
            continue
        try:
            budgets = json.loads(raw).get("budgets") or {}
        except ValueError:
            continue
        if budgets.get("energy") != 0:
            break
        streak += 1
    return streak


def _role_verbs(role: str) -> set[str]:
    spec = ROLES.get(role) or {}
    return set(spec.get("verbs") or ()) | {"BUILD", "ORG_INVITE"}


def open_db(root: Path) -> sqlite3.Connection:
    path = root / "shared" / "metrics.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.executescript(_SCHEMA)
    return db


def collect(root: Path, db: sqlite3.Connection) -> int:
    """Ingest new lines from every agent log. Returns sessions added."""
    added = 0
    for log in sorted((root / "logs").glob("noema-*.log")):
        src = log.name
        row = db.execute("SELECT offset FROM marks WHERE src=?", (src,)).fetchone()
        start = row[0] if row else 0
        lines = log.read_text(errors="replace").splitlines()
        if start > len(lines):  # log rotated or truncated
            start = 0
        role, turns, role_n, idle_n, drops = None, 0, 0, 0, 0
        done = start  # resume after the last complete session so partial sessions are re-read whole
        for n, raw in enumerate(lines[start:], start=start):
            if not raw.startswith("{"):
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if "turn" in d and "action" in d:
                turns += 1
                act = str(d.get("action") or "").upper()
                if role and act in _role_verbs(role):
                    role_n += 1
                elif act in IDLE:
                    idle_n += 1
            elif "transport_drop" in d:
                drops += 1
            elif "role" in d and "stop_reason" not in d:
                role = d.get("role")
            elif "stop_reason" in d:
                role = d.get("role") or role
                db.execute("INSERT OR IGNORE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (src, n, time.time(), d.get("member"), role, d.get("actions"), d.get("stop_reason"),
                            d.get("stop_detail"), role_n, idle_n, turns, drops,
                            json.dumps((d.get("rejections") or {}).get("by_verb_code") or {})))
                added += 1
                rsi = d.get("rsi")
                if isinstance(rsi, dict) and rsi.get("verdict"):
                    db.execute(
                        "INSERT OR IGNORE INTO rsi_events VALUES (?,?,?,?,?,?,?)",
                        (src, n, time.time(), d.get("member"), str(rsi.get("verdict")),
                         float(rsi.get("fitness") or 0.0), str(rsi.get("reason") or "")[:200]),
                    )
                health = d.get("health") or {}
                if isinstance(health, dict) and "workers_ai_calls" in health:
                    # health counters are cumulative per process; store the delta (reset on restart).
                    calls, fb = int(health.get("workers_ai_calls") or 0), int(health.get("ollama_fallbacks") or 0)
                    prev = db.execute("SELECT calls_total, fallbacks_total FROM cost_marks WHERE src=?", (src,)).fetchone()
                    dc, df = (calls - prev[0], fb - prev[1]) if prev and calls >= prev[0] else (calls, fb)
                    db.execute("INSERT OR IGNORE INTO cost VALUES (?,?,?,?,?)", (src, n, time.time(), dc, max(df, 0)))
                    db.execute("INSERT INTO cost_marks VALUES (?,?,?) ON CONFLICT(src) DO UPDATE SET "
                               "calls_total=excluded.calls_total, fallbacks_total=excluded.fallbacks_total", (src, calls, fb))
                done = n + 1
                turns, role_n, idle_n, drops = 0, 0, 0, 0
        db.execute("INSERT INTO marks VALUES (?,?) ON CONFLICT(src) DO UPDATE SET offset=excluded.offset", (src, done))
        db.execute("INSERT INTO stuck VALUES (?,?,?) ON CONFLICT(src) DO UPDATE SET zero_energy_streak=excluded.zero_energy_streak, "
                   "ts=excluded.ts", (src, zero_energy_streak(lines[-400:]), time.time()))
    db.commit()
    return added


def digest(db: sqlite3.Connection, hours: float = 24) -> dict:
    since = time.time() - hours * 3600
    rows = db.execute("SELECT member, role, count(*), sum(stop_reason='duration_elapsed'), sum(turns), sum(role_actions), "
                      "sum(idle_actions), sum(drops) FROM sessions WHERE ts >= ? GROUP BY member ORDER BY member", (since,)).fetchall()
    stale_by_member: dict[str, int] = {}
    for m_name, rej_raw in db.execute("SELECT member, rejections FROM sessions WHERE ts >= ?", (since,)).fetchall():
        try:
            rej_obj = json.loads(rej_raw or "{}")
        except ValueError:
            rej_obj = {}
        if isinstance(rej_obj, dict):
            stale_n = sum(int(v) for k, v in rej_obj.items() if str(k).endswith(":STALE_HEAD") and isinstance(v, (int, float)))
            stale_by_member[m_name] = stale_by_member.get(m_name, 0) + stale_n
    out = {}
    for member, role, n, full, turns, role_n, idle_n, drops in rows:
        turns = turns or 0
        stale_n = stale_by_member.get(member, 0)
        out[member] = {"role": role, "sessions": n, "full_sessions": full or 0, "turns": turns,
                       "role_action_rate": round((role_n or 0) / turns, 3) if turns else 0.0,
                       "idle_rate": round((idle_n or 0) / turns, 3) if turns else 0.0, "drops": drops or 0,
                       "stale_head_rejections": stale_n,
                       "stale_head_rate": round(stale_n / turns, 3) if turns else 0.0}
    alerts = [f"{m}: idle_rate {v['idle_rate']}" for m, v in out.items() if v["turns"] >= 20 and v["idle_rate"] > 0.6]
    alerts += [f"{m}: {v['sessions'] - v['full_sessions']}/{v['sessions']} sessions ended early" for m, v in out.items()
               if v["sessions"] >= 4 and v["full_sessions"] / v["sessions"] < 0.5]
    for src, streak in db.execute("SELECT src, zero_energy_streak FROM stuck WHERE zero_energy_streak >= ? ORDER BY src",
                                  (STUCK_TURNS,)).fetchall():
        member = src.removeprefix("noema-player@").removeprefix("noema-").removesuffix(".log")
        alerts.append(f"{member}: energy 0 for last {streak} turns (Noema#907)")
    alerts += cost_alerts(db, hours)
    for member, reason in db.execute(
        "SELECT member, reason FROM rsi_events WHERE ts >= ? AND verdict = 'ROLLED_BACK' ORDER BY ts DESC",
        (since,),
    ).fetchall():
        alerts.append(f"{member}: rsi_rollback ({reason or 'regression'})")
    return {"window_hours": hours, "members": out, "alerts": alerts}


def cost_alerts(db: sqlite3.Connection, hours: float = 24) -> list[str]:
    """S15: one line when model calls near the daily cap or Ollama fallbacks exceed 5% of calls."""
    calls, fallbacks = db.execute("SELECT coalesce(sum(calls),0), coalesce(sum(fallbacks),0) FROM cost WHERE ts >= ?",
                                  (time.time() - hours * 3600,)).fetchone()
    out = []
    if calls >= CAP_ALARM * DAILY_CALL_CAP * hours / 24:
        out.append(f"cost: {calls} model calls in {hours:g}h (cap {DAILY_CALL_CAP}/day)")
    if calls >= 100 and fallbacks / calls > FALLBACK_ALARM:
        out.append(f"cost: Ollama fallbacks {fallbacks}/{calls} ({fallbacks / calls:.0%})")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path.home() / "noema-players")
    ap.add_argument("--digest", action="store_true", help="print a 24h digest after collecting")
    ap.add_argument("--hours", type=float, default=24)
    ns = ap.parse_args(argv)
    with contextlib.closing(open_db(ns.root)) as db:
        added = collect(ns.root, db)
        if ns.digest:
            d = digest(db, ns.hours)
            print(json.dumps({"digest": d}, sort_keys=True))
            os.makedirs(ns.root / "shared", exist_ok=True)
            (ns.root / "shared" / "digest.json").write_text(json.dumps(d, indent=1, sort_keys=True))
        else:
            print(json.dumps({"metrics_added": added}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
