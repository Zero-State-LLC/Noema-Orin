"""Read-only fleet state aggregator and incremental JSONL log tailer (D1/#181).

Opens every SQLite database strictly read-only (`?mode=ro`) so the dashboard can never
block an active Orin agent turn. Never reads or returns raw token or credential strings.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ..jetson_telemetry import collect_jetson_telemetry
from ..llm_client import fetch_llama_metrics
from ..metrics import digest as metrics_digest
from ..roles import ROLES
from ..rsi import KNOB_SPECS, load_agenda
from ..shop_planner import ROLE_LOADOUTS
from ..token_watch import check as check_tokens
from .controls import ALLOWED_UNITS

RESIDENT_MEMBERS = ("m01", "m02", "m03", "m04", "m05", "m06")
_SAFE_OVERRIDE_KEYS = ("NOEMA_INFERENCE_MODE", "NOEMA_GROUNDED_VOICE")
# Alerts that are expected for energy-limited roles: shown muted, never in the banner.
_EXPECTED_ALERT_MARKERS = ("idle_rate",)
RAM_WARN_MIB = 1024
SNAPSHOT_TTL_S = 2.0
ROLE_SPARK_WINDOW = 50
_EMPTY_LOG_SUMMARY: dict[str, Any] = {
    "last_turn": None, "recent_turns": [], "last_session": None, "source_counts": {},
    "role_spark": [], "turns_since_role": None, "last_role_action": None,
}


def classify_alerts(raw: list[str], *, hw: dict[str, Any], units: dict[str, dict]) -> list[dict[str, str]]:
    """Tag digest alerts crit/warn/expected and add live health alerts (RAM floor, dead infra units)."""
    out: list[dict[str, str]] = []
    for text in raw:
        t = str(text)
        if any(mk in t for mk in _EXPECTED_ALERT_MARKERS):
            level = "expected"
        elif "rollback" in t or "energy 0" in t or "traceback" in t.lower() or "INCIDENT" in t:
            level = "crit"
        else:
            level = "warn"
        out.append({"level": level, "text": t})
    mem = hw.get("mem_avail_mib")
    if isinstance(mem, (int, float)) and mem < RAM_WARN_MIB:
        out.append({"level": "crit" if mem < 512 else "warn", "text": f"RAM available {int(mem)} MiB (< {RAM_WARN_MIB})"})
    for unit, st in (units or {}).items():
        state = (st or {}).get("active_state")
        if state in ("failed", "inactive") and not unit.startswith("noema-player@"):
            out.append({"level": "crit", "text": f"{unit} {state}"})
    return out


def _client_map(map_state: dict[str, Any]) -> dict[str, Any]:
    """Map as sent to browsers: positions/equipment are server-side inputs (agents carry room_id)."""
    return {k: v for k, v in map_state.items() if k not in ("positions", "equipment", "max_seq")}


def _strip_seen(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_seen(v) for k, v in obj.items() if not str(k).endswith("seen_seq")}
    if isinstance(obj, list):
        return [_strip_seen(v) for v in obj]
    return obj


def _map_signature(map_state: dict[str, Any]) -> str:
    """Content hash of what the map draws. Ignores re-observation stamps, which change every turn."""
    body = _strip_seen(_client_map(map_state))
    return hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]


def _ro_connect(path: Path) -> sqlite3.Connection | None:
    if not path.is_file():
        return None
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        db.row_factory = sqlite3.Row
        return db
    except sqlite3.Error:
        return None


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (ValueError, OSError):
        return default


def _table_exists(db: sqlite3.Connection, name: str) -> bool:
    row = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


class DashboardStateReader:
    """Aggregates live fleet state from ~/noema-players/ strictly read-only."""

    def __init__(
        self,
        *,
        root: Path,
        config_dir: Path,
        systemd_runner=None,
        llama_base_url: str | None = None,
        sysfs_probe=None,
    ) -> None:
        self.sysfs_probe = sysfs_probe
        self.root = Path(root)
        self.config_dir = Path(config_dir)
        self.systemd_runner = systemd_runner
        self.llama_base_url = llama_base_url or os.environ.get("NOEMA_LOCAL_LLM_BASE", "http://127.0.0.1:8081/v1")
        self._log_offsets: dict[str, int] = {}
        self._snap_cache: tuple[float, dict[str, Any]] | None = None
        self._snap_lock = threading.Lock()
        self._rate_prev: dict[str, tuple[float, float]] = {}

    def cached_snapshot(self, ttl: float = SNAPSHOT_TTL_S) -> dict[str, Any]:
        """One snapshot per TTL shared by every viewer (kiosk + tunnels), so N viewers cost 1 build."""
        with self._snap_lock:
            now = time.monotonic()
            if self._snap_cache is not None and now - self._snap_cache[0] < ttl:
                return self._snap_cache[1]
            snap = self.snapshot()
            self._snap_cache = (now, snap)
            return snap

    def _rate_per_min(self, key: str, counter: float | None) -> float | None:
        """Per-minute rate of a monotonically increasing counter between snapshots."""
        if not isinstance(counter, (int, float)):
            return None
        now = time.monotonic()
        prev = self._rate_prev.get(key)
        self._rate_prev[key] = (now, float(counter))
        if prev is None or now - prev[0] < 1.0 or counter < prev[1]:
            return None
        return round((counter - prev[1]) * 60.0 / (now - prev[0]), 1)

    def _roles_map(self) -> dict[str, str]:
        p = self.root / "roles.tsv"
        if not p.is_file():
            return {"m01": "founder", "m02": "quartermaster", "m03": "custodian", "m04": "archivist", "m05": "speaker", "m06": "surveyor"}
        out = {}
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if "\t" in line:
                m, r = line.split("\t", 1)
                out[m.strip()] = r.strip()
        return out

    def _cohort_map(self) -> dict[str, str]:
        p = self.root / "shared" / "cohort.tsv"
        if not p.is_file():
            return {}
        out = {}
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if "\t" in line:
                m, pid = line.split("\t", 1)
                out[m.strip()] = pid.strip()
        return out

    def _agent_mode(self, member: str, fleet: dict[str, str]) -> dict[str, Any]:
        """Effective inference mode per agent: runtime-overrides.env loads after mXX.env, so it wins."""
        mode, embed = None, False
        p = self.config_dir / f"{member}.env"
        try:
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" not in line or line.lstrip().startswith("#"):
                    continue
                k, v = (s.strip() for s in line.split("=", 1))
                if k == "NOEMA_INFERENCE_MODE":
                    mode = v.strip('"')
                elif k == "NOEMA_TRT_EMBED_URL" and v.strip('"'):
                    embed = True
        except OSError:
            pass
        ov_file = self.config_dir / "runtime-overrides.env"
        if ov_file.is_file() and "NOEMA_INFERENCE_MODE" in ov_file.read_text(encoding="utf-8", errors="replace"):
            mode = fleet.get("NOEMA_INFERENCE_MODE", mode)
        return {"inference_mode": mode or "cloud_first", "semantic_memory": embed}

    def _runtime_overrides(self) -> dict[str, str]:
        p = self.config_dir / "runtime-overrides.env"
        out = {
            "NOEMA_INFERENCE_MODE": os.environ.get("NOEMA_INFERENCE_MODE", "cloud_first"),
            "NOEMA_GROUNDED_VOICE": os.environ.get("NOEMA_GROUNDED_VOICE", "0"),
        }
        if p.is_file():
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k in _SAFE_OVERRIDE_KEYS:
                        out[k] = v.strip().strip('"')
        return out

    def _read_map(self) -> dict[str, Any]:
        empty = {
            "rooms": [],
            "exits": [],
            "positions": {},
            "scars": [],
            "pressure": {},
            "stalls": [],
            "listings": [],
            "shared_work": [],
            "claims": [],
            "equipment": [],
            "max_seq": 0,
        }
        db = _ro_connect(self.root / "shared" / "map.db")
        if db is None:
            return empty
        with contextlib.closing(db):
            rooms = [dict(r) for r in db.execute("SELECT room_id, name, last_seen_seq FROM rooms ORDER BY room_id").fetchall()] if _table_exists(db, "rooms") else []
            exits = [dict(r) for r in db.execute("SELECT room_id, dest FROM exits").fetchall()] if _table_exists(db, "exits") else []
            positions: dict[str, dict] = {}
            if _table_exists(db, "positions"):
                for r in db.execute("SELECT player_id, room_id, energy, free_storage, seen_seq FROM positions").fetchall():
                    positions[str(r["player_id"])] = dict(r)
            scars = [dict(r) for r in db.execute("SELECT room_id, scar_id, domain, strength, confidence, seen_seq FROM room_scars").fetchall()] if _table_exists(db, "room_scars") else []
            pressure: dict[str, dict] = {}
            if _table_exists(db, "room_pressure"):
                for r in db.execute("SELECT room_id, harvest_pressure, protocol_strength, seen_seq FROM room_pressure").fetchall():
                    pressure[str(r["room_id"])] = dict(r)
            stalls = [dict(r) for r in db.execute("SELECT stall_id, room_id, owner_id, condition, open_listings, seen_seq FROM shop_stalls").fetchall()] if _table_exists(db, "shop_stalls") else []
            listings = [dict(r) for r in db.execute("SELECT listing_id, stall_id, room_id, owner_id, listing_kind, offer_json, ask_json, fills_remaining, seen_seq FROM shop_listings WHERE fills_remaining > 0 ORDER BY seen_seq DESC").fetchall()] if _table_exists(db, "shop_listings") else []
            shared_work = [dict(r) for r in db.execute("SELECT room_id, action, target_id, condition, observer_id, seen_seq FROM shared_work ORDER BY coalesce(condition,100) ASC").fetchall()] if _table_exists(db, "shared_work") else []
            max_seq = max(
                [int(r.get("last_seen_seq") or 0) for r in rooms]
                + [int(p.get("seen_seq") or 0) for p in positions.values()],
                default=0,
            )
            claims = []
            if _table_exists(db, "cohort_claims"):
                claims = [
                    dict(r)
                    for r in db.execute(
                        "SELECT target_id, member, action, claimed_seq, expires_seq FROM cohort_claims WHERE expires_seq > ? ORDER BY expires_seq DESC",
                        (max_seq - 1 if max_seq > 0 else -1,),
                    ).fetchall()
                ]
            equipment = [dict(r) for r in db.execute("SELECT player_id, item_id, archetype, category, equip_slot, equipped_slot, condition, max_condition, seen_seq FROM equipment_state").fetchall()] if _table_exists(db, "equipment_state") else []
        return {
            "rooms": rooms,
            "exits": exits,
            "positions": positions,
            "scars": scars,
            "pressure": pressure,
            "stalls": stalls,
            "listings": listings,
            "shared_work": shared_work,
            "claims": claims,
            "equipment": equipment,
            "max_seq": max_seq,
        }

    def _recent_log_summary(self, member: str, max_turns: int = 20, role_verbs: frozenset[str] = frozenset()) -> dict[str, Any]:
        log_path = self.root / "logs" / f"noema-player@{member}.log"
        if not log_path.is_file():
            return dict(_EMPTY_LOG_SUMMARY)
        try:
            with log_path.open("rb") as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - 65536))
                chunk = fh.read().decode("utf-8", errors="replace")
        except OSError:
            return dict(_EMPTY_LOG_SUMMARY)

        turns: list[dict] = []
        last_session: dict | None = None
        sources: dict[str, int] = {}
        for raw in chunk.splitlines():
            if not raw.startswith("{"):
                continue
            try:
                d = json.loads(raw)
            except ValueError:
                continue
            if "turn" in d and "action" in d:
                turns.append(d)
                src = str(d.get("source") or "unknown")
                sources[src] = sources.get(src, 0) + 1
            elif "stop_reason" in d:
                last_session = d
        recent = turns[-max_turns:]
        window = turns[-ROLE_SPARK_WINDOW:]
        # 1/0 per turn over the last 50: did this turn use a role verb? Drives the card sparkline.
        spark = [1 if str(t.get("action") or "") in role_verbs else 0 for t in window]
        last_role = next((t for t in reversed(turns) if str(t.get("action") or "") in role_verbs), None)
        return {
            "last_turn": recent[-1] if recent else None,
            "recent_turns": recent,
            "last_session": last_session,
            "source_counts": sources,
            "role_spark": spark,
            "turns_since_role": (len(turns) - 1 - turns.index(last_role)) if last_role is not None else None,
            "last_role_action": f"{last_role.get('action')} {last_role.get('target') or ''}".strip() if last_role else None,
        }

    def _read_metrics_digest(self) -> dict[str, Any]:
        db = _ro_connect(self.root / "shared" / "metrics.db")
        if db is not None:
            with contextlib.closing(db):
                try:
                    return metrics_digest(db, hours=24)
                except sqlite3.Error:
                    pass
        return _read_json(self.root / "shared" / "digest.json", {"window_hours": 24, "members": {}, "alerts": []})

    def _read_audit(self, limit: int = 30) -> list[dict]:
        p = self.root / "logs" / "dashboard-audit.jsonl"
        if not p.is_file():
            return []
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        out = []
        for raw in reversed(lines):
            try:
                row = json.loads(raw)
                if isinstance(row, dict):
                    out.append(row)
            except ValueError:
                continue
        return out

    def snapshot(self) -> dict[str, Any]:
        roles = self._roles_map()
        cohort = self._cohort_map()
        map_state = self._read_map()
        dig = self._read_metrics_digest()
        unit_states = (
            self.systemd_runner.unit_statuses(ALLOWED_UNITS)
            if self.systemd_runner is not None
            else {u: {"active_state": "unknown", "sub_state": "unknown", "since": ""} for u in ALLOWED_UNITS}
        )

        # Hardware telemetry: prefer live sysfs/llama, fall back to latest metrics.db hw_samples
        llama_metrics = fetch_llama_metrics(self.llama_base_url, timeout=0.6) if self.llama_base_url else {}
        live_hw = collect_jetson_telemetry(probe=self.sysfs_probe, llama_metrics=llama_metrics)
        db_hw = dig.get("hw") if isinstance(dig.get("hw"), dict) else {}
        hw = {}
        for k, v in live_hw.items():
            hw[k] = db_hw.get(k) if v == "NOT_COMPUTABLE" and db_hw.get(k) is not None else v

        tok_code, tok_rows = check_tokens(self.config_dir, warn_days=7.0) if self.config_dir.is_dir() else (0, [])

        equip_by_player: dict[str, list[dict]] = {}
        for it in map_state["equipment"]:
            equip_by_player.setdefault(str(it["player_id"]), []).append(it)

        agents = []
        recent_feed: list[dict] = []
        inference_totals = {"planner": 0, "local_s1": 0, "workers_ai": 0, "fallback": 0, "idle_skip": 0}
        for member in sorted(set(RESIDENT_MEMBERS) | set(roles)):
            role = roles.get(member, "unknown")
            if role == "maintenance":
                continue
            mind = self.root / member / "mind"
            persona = _read_json(mind / "persona.json", {"name": member, "role": role, "version": 0, "traits": {}})
            knobs = _read_json(mind / "policy_knobs.json", {})
            agenda = load_agenda(mind)
            rsi_state = _read_json(mind / "rsi_state.json", {})
            pid = cohort.get(member, f"player.{persona.get('name', member)}-{role.capitalize()}")
            pos = map_state["positions"].get(pid, {})
            role_verbs = frozenset((ROLES.get(role) or {}).get("verbs") or ())
            log_sum = self._recent_log_summary(member, max_turns=15, role_verbs=role_verbs)
            last_turn = log_sum["last_turn"] or {}
            last_sess = log_sum["last_session"] or {}
            sess_health = last_sess.get("health") if isinstance(last_sess.get("health"), dict) else {}
            m_dig = (dig.get("members") or {}).get(member, {})
            unit_name = f"noema-player@{member}"
            ust = unit_states.get(unit_name, {})

            items = equip_by_player.get(pid, [])
            min_cond = min((int(it.get("condition") or 0) for it in items if it.get("archetype") != "depleted_cell"), default=None)
            loadout_want = list(ROLE_LOADOUTS.get(role, ()))
            loadout_held = sorted({str(it.get("archetype") or "") for it in items if int(it.get("condition") or 0) > 0})

            cand = rsi_state.get("candidate")
            rsi_status = (
                "PAUSED"
                if rsi_state.get("paused")
                else f"CANARY {len(cand.get('scores') or [])}/3"
                if isinstance(cand, dict)
                else "BASELINE"
            )

            budgets = last_turn.get("budgets") if isinstance(last_turn.get("budgets"), dict) else {}
            if "energy" not in budgets and pos.get("energy") is not None:
                budgets = {**budgets, "energy": pos["energy"]}
            if "storage" not in budgets and pos.get("free_storage") is not None:
                budgets = {**budgets, "storage": pos["free_storage"]}

            for src_k, cnt in log_sum["source_counts"].items():
                if src_k in inference_totals:
                    inference_totals[src_k] += cnt
                elif src_k == "model":
                    inference_totals["workers_ai"] += cnt
            inference_totals["local_s1"] += int(sess_health.get("local_s1_calls") or 0)

            for tr in log_sum["recent_turns"][-6:]:
                recent_feed.append({"member": member, "role": role, "handle": pid.replace("player.", "", 1), **tr})

            active_step = next(
                (s for s in (agenda.get("steps") or []) if isinstance(s, dict) and s.get("status") in ("active", "pending")),
                None,
            )

            hw_embed_n = 0
            mdb = _ro_connect(mind / "memory.db")
            if mdb is not None:
                with contextlib.closing(mdb):
                    with contextlib.suppress(sqlite3.Error):
                        if _table_exists(mdb, "fact_embeddings"):
                            hw_embed_n = int(mdb.execute("SELECT count(*) FROM fact_embeddings").fetchone()[0])

            agents.append(
                {
                    "embedding_count": hw_embed_n,
                    "member": member,
                    "unit": unit_name,
                    "role": role,
                    "handle": pid.replace("player.", "", 1),
                    "player_id": pid,
                    "persona_name": persona.get("name", member),
                    "persona_version": int(persona.get("version") or 0),
                    "unit_state": ust.get("active_state", "unknown"),
                    **self._agent_mode(member, self._runtime_overrides()),
                    "unit_since": ust.get("since", ""),
                    "room_id": last_turn.get("room") or pos.get("room_id"),
                    "budgets": budgets,
                    "last_action": last_turn.get("action"),
                    "last_target": last_turn.get("target"),
                    "last_source": last_turn.get("source"),
                    "last_tier": last_turn.get("tier"),
                    "held_tracks": list(agenda.get("held_tracks") or []),
                    "desired_tracks": list((ROLES.get(role) or {}).get("focus_tracks") or ()),
                    "active_step": active_step,
                    "agenda_epoch": int(agenda.get("epoch") or 0),
                    "loadout_want": loadout_want,
                    "loadout_held": loadout_held,
                    "min_tool_condition": min_cond,
                    "role_action_rate": m_dig.get("role_action_rate", 0.0),
                    "role_spark": log_sum["role_spark"],
                    "role_rate_recent": round(sum(log_sum["role_spark"]) / len(log_sum["role_spark"]), 3) if log_sum["role_spark"] else 0.0,
                    "turns_since_role": log_sum["turns_since_role"],
                    "last_role_action": log_sum["last_role_action"],
                    "idle_rate": m_dig.get("idle_rate", 0.0),
                    "stale_head_rate": m_dig.get("stale_head_rate", 0.0),
                    "consequence": m_dig.get("consequence"),  # C4 (#199): INFERRED shadow accuracy; None when shadow is off
                    "turns_24h": m_dig.get("turns", 0),
                    "rejections": (last_sess.get("rejections") or {}).get("by_verb_code") or {},
                    "rsi_status": rsi_status,
                    "rsi_baseline": rsi_state.get("baseline_fitness"),
                    "rsi_paused": bool(rsi_state.get("paused", False)),
                    "knobs": knobs,
                }
            )

        home_org_path = self.root / "shared" / "home_org"
        home_org = home_org_path.read_text(encoding="utf-8").strip() if home_org_path.is_file() else ""
        recent_feed.sort(key=lambda r: int(r.get("turn") or 0), reverse=True)
        map_sig = _map_signature(map_state)
        hw["llama_req_per_min"] = self._rate_per_min("llama", llama_metrics.get("llamacpp:n_decode_total")
                                                     if llama_metrics.get("llamacpp:n_decode_total") is not None
                                                     else llama_metrics.get("llamacpp:tokens_predicted_total"))
        emb_total = sum(int(a.get("embedding_count") or 0) for a in agents)
        hw["embed_per_min"] = self._rate_per_min("embed", emb_total if agents else None)

        return {
            "map_sig": map_sig,
            "alert_items": classify_alerts(list(dig.get("alerts") or []), hw=hw, units=unit_states),
            "ts": round(time.time(), 2),
            "home_org": home_org,
            "world_seq": map_state["max_seq"],
            "units": unit_states,
            "agents": agents,
            "map": _client_map(map_state),
            "hw": hw,
            "tokens": tok_rows,
            "token_status_code": tok_code,
            "alerts": list(dig.get("alerts") or []),
            "inference_totals": inference_totals,
            "runtime_overrides": self._runtime_overrides(),
            "knob_specs": {
                k: {"default": v[0], "min": v[1], "max": v[2], "is_int": v[3]}
                for k, v in KNOB_SPECS.items()
            },
            "recent_turns": recent_feed[:40],
            "audit": self._read_audit(limit=20),
        }

    def agent_detail(self, member: str, *, query: str = "") -> dict[str, Any]:
        """Deep read-only inspection of one agent's private mind (persona lineage, agenda, memory, RSI)."""
        if member not in RESIDENT_MEMBERS:
            raise ValueError("unknown member")
        mind = self.root / member / "mind"
        persona = _read_json(mind / "persona.json", {})
        knobs = _read_json(mind / "policy_knobs.json", {})
        agenda = load_agenda(mind)
        rsi_state = _read_json(mind / "rsi_state.json", {})
        versions = sorted(p.name for p in mind.glob("persona.v*.json")) if mind.is_dir() else []
        quarantine: list[dict] = []
        qpath = mind / "quarantine.jsonl"
        if qpath.is_file():
            for line in qpath.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]:
                try:
                    quarantine.append(json.loads(line))
                except ValueError:
                    continue

        facts: list[dict] = []
        relations: list[dict] = []
        embed_count = 0
        db = _ro_connect(mind / "memory.db")
        if db is not None:
            with contextlib.closing(db):
                if _table_exists(db, "facts"):
                    q = " ".join(c if c.isalnum() else " " for c in query).strip()
                    if q and _table_exists(db, "facts_fts"):
                        terms = [t for t in q.split() if len(t) > 2][:8]
                        if terms:
                            facts = [
                                dict(r)
                                for r in db.execute(
                                    "SELECT f.kind, f.room, f.text, f.source_sequence, f.stale "
                                    "FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
                                    "WHERE facts_fts MATCH ? ORDER BY rank LIMIT 30",
                                    (" OR ".join(terms),),
                                ).fetchall()
                            ]
                    else:
                        facts = [
                            dict(r)
                            for r in db.execute(
                                "SELECT kind, room, text, source_sequence, stale FROM facts "
                                "WHERE stale=0 ORDER BY coalesce(source_sequence,0) DESC, id DESC LIMIT 30"
                            ).fetchall()
                        ]
                if _table_exists(db, "relations"):
                    relations = [
                        dict(r)
                        for r in db.execute(
                            "SELECT player_id, note, sign, sequence FROM relations ORDER BY rowid DESC LIMIT 30"
                        ).fetchall()
                    ]
                if _table_exists(db, "fact_embeddings"):
                    embed_count = int(db.execute("SELECT count(*) FROM fact_embeddings").fetchone()[0])

        return {
            "member": member,
            "persona": persona,
            "persona_versions": versions,
            "knobs": knobs,
            "agenda": agenda,
            "rsi_state": rsi_state,
            "quarantine": quarantine,
            "facts": facts,
            "relations": relations,
            "embedding_count": embed_count,
        }

    def poll_new_turns(self, offsets: dict[str, int] | None = None) -> list[dict[str, Any]]:
        """Incrementally tail member log files and return newly appended JSONL turn/session events."""
        events: list[dict[str, Any]] = []
        logs_dir = self.root / "logs"
        if not logs_dir.is_dir():
            return events
        offs = self._log_offsets if offsets is None else offsets
        roles = self._roles_map()
        for log_path in sorted(logs_dir.glob("noema-player@m*.log")):
            name = log_path.name
            member = name.split("@", 1)[1].split(".", 1)[0]
            role = roles.get(member, "unknown")
            role_verbs = (ROLES.get(role) or {}).get("verbs") or ()
            try:
                size = log_path.stat().st_size
            except OSError:
                continue
            if name not in offs:
                # First sight of this log: start at EOF so viewers get live turns, not hours of replay.
                offs[name] = size
                continue
            prev = offs[name]
            if prev > size:
                prev = 0  # rotated or truncated
            if prev == size:
                continue
            try:
                with log_path.open("rb") as fh:
                    fh.seek(prev)
                    raw = fh.read(131072)
                    offs[name] = fh.tell()
            except OSError:
                continue
            for line in raw.decode("utf-8", errors="replace").splitlines():
                if not line.startswith("{"):
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if "turn" in d and "action" in d:
                    events.append({"event": "turn", "member": member, "role": role,
                                   "is_role": str(d.get("action") or "") in role_verbs, **d})
                elif "stop_reason" in d:
                    events.append({"event": "session_end", "member": member, **d})
        return events
