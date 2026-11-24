"""Background replication of Controller-local memory to a private D1 (D-013, #36).

Runs from a systemd timer, never inside an agent turn. Reads each member's
memory.db and the shared map read-only, sends rows changed since the last
high-water mark, and records the mark only after a 2xx. Network failure leaves
local memory untouched and is retried on the next tick.
"""

import argparse
import json
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path


def _ro(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    return db


def collect(root: Path, member: str, marks: dict) -> dict:
    mark = marks.get(member, {})
    out: dict = {"member": member, "facts": [], "relations": [], "rooms": [], "exits": [], "offers": []}
    mem = _ro(root / member / "mind" / "memory.db")
    if mem is not None:
        out["facts"] = [dict(r) for r in mem.execute(
            "SELECT id, sequence, room, kind, text, source_sequence, stale FROM facts WHERE coalesce(sequence,0) > ? "
            "ORDER BY sequence LIMIT 2000", (mark.get("facts_seq", -1),))]
        out["relations"] = [dict(r) for r in mem.execute(
            "SELECT rowid, player_id, note, sign, sequence FROM relations WHERE rowid > ? ORDER BY rowid LIMIT 2000",
            (mark.get("rel_rowid", 0),))]
        mem.close()
    persona = root / member / "mind" / "persona.json"
    if persona.exists():
        body = json.loads(persona.read_text())
        if body.get("version") != mark.get("persona_version"):
            out["persona"] = body
    shared = _ro(root / "shared" / "map.db")
    if shared is not None and member == "_map":
        out["rooms"] = [dict(r) for r in shared.execute("SELECT * FROM rooms WHERE last_seen_seq > ?", (mark.get("map_seq", -1),))]
        out["offers"] = [dict(r) for r in shared.execute("SELECT * FROM offers WHERE seen_seq > ?", (mark.get("map_seq", -1),))]
        out["exits"] = [dict(r) for r in shared.execute("SELECT * FROM exits")]
        shared.close()
    return out


def advance(marks: dict, payload: dict) -> dict:
    m = dict(marks.get(payload["member"], {}))
    if payload["facts"]:
        m["facts_seq"] = max(f["sequence"] or 0 for f in payload["facts"])
    if payload["relations"]:
        m["rel_rowid"] = max(r["rowid"] for r in payload["relations"])
    if payload.get("persona"):
        m["persona_version"] = payload["persona"].get("version")
    if payload["rooms"] or payload["offers"]:
        m["map_seq"] = max([r["last_seen_seq"] for r in payload["rooms"]] + [o["seen_seq"] for o in payload["offers"]])
    return {**marks, payload["member"]: m}


def empty(payload: dict) -> bool:
    return not any(payload[k] for k in ("facts", "relations", "rooms", "offers")) and not payload.get("persona")


def post(url: str, token: str, payload: dict) -> dict:
    req = urllib.request.Request(url.rstrip("/") + "/sync", data=json.dumps(payload, default=str).encode(), method="POST",
                                 headers={"authorization": f"Bearer {token}", "content-type": "application/json",
                                          "user-agent": "noema-orin-memory-sync/1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Replicate Orin agent memory to private D1")
    ap.add_argument("--root", type=Path, default=Path.home() / "noema-players")
    ns = ap.parse_args(argv)
    url, token = os.environ.get("MEMORY_SYNC_URL"), os.environ.get("MEMORY_SYNC_TOKEN")
    if not url or not token:
        print(json.dumps({"status": "NOT_CONFIGURED"}))
        return 0
    state = ns.root / "shared" / "sync-marks.json"
    marks = json.loads(state.read_text()) if state.exists() else {}
    members = sorted(p.name for p in ns.root.iterdir() if (p / "mind").is_dir()) + ["_map"]
    sent = {}
    for member in members:
        payload = collect(ns.root, member, marks)
        if empty(payload):
            continue
        try:
            result = post(url, token, payload)
        except Exception as exc:
            print(json.dumps({"member": member, "status": "RETRY_LATER", "error": type(exc).__name__}))
            continue
        marks = advance(marks, payload)
        sent[member] = result.get("written")
    state.write_text(json.dumps(marks))
    print(json.dumps({"status": "OK", "written": sent}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
