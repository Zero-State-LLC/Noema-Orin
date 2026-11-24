"""Persistent civic Player loop for one Orin member (D-009).

Needs the official ``noema-client`` (Python >=3.11) and an approved credential in the
member's own config dir. Runs bounded ``play`` sessions back to back until SIGTERM.
Decisions come from an OpenAI-compatible endpoint (local Ollama by default).
"""

import argparse
import json
import os
import signal
import sys
import threading
from pathlib import Path

from .roles import DENY_ALWAYS, role_for


def build_policy(role: str):
    from noema_client.policy import ClientPolicy

    spec = role_for(role)
    return ClientPolicy(allow_trade=False, allow_access=False, allow_contest=False,
                        allowed_actions=list(spec["allow"]), denied_actions=list(DENY_ALWAYS),
                        max_consecutive_failures=3)


def stagger(members: list[str], member: str, cooldown: float, turn_gap: float) -> tuple[float, float]:
    """Spread one shared model across the cohort: cooldown grows with cohort size, starts are offset."""
    n = max(1, len(members))
    cool = max(cooldown, turn_gap * n)
    idx = members.index(member) if member in members else 0
    return cool, round(idx * cool / n, 1)


def cohort_ids(root: Path) -> set[str]:
    """Player ids the Orin agents have observed for themselves (shared/cohort.tsv)."""
    path = root / "shared" / "cohort.tsv"
    if not path.exists():
        return set()
    return {line.split("\t")[1] for line in path.read_text().splitlines() if "\t" in line}


def record_self(root: Path, member: str, player_id: str | None) -> None:
    if not player_id:
        return
    path = root / "shared" / "cohort.tsv"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = dict(line.split("\t", 1) for line in path.read_text().splitlines() if "\t" in line) if path.exists() else {}
    if rows.get(member) != player_id:
        rows[member] = player_id
        path.write_text("".join(f"{k}\t{v}\n" for k, v in sorted(rows.items())))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Persistent Orin civic Player")
    ap.add_argument("--member", required=True)
    ap.add_argument("--root", type=Path, default=Path.home() / "noema-players")
    ap.add_argument("--session-seconds", type=float, default=1800)
    ap.add_argument("--cooldown", type=float, default=20)
    ap.add_argument("--turn-gap", type=float, default=8, help="seconds of model time reserved per cohort member (T19)")
    ns = ap.parse_args(argv)
    roles = dict(line.split("\t") for line in (ns.root / "roles.tsv").read_text().split("\n") if "\t" in line)
    role = roles.get(ns.member)
    role_for(role)
    from noema_client.client import NoemaClient

    from .orin_adapter import from_env, reflect
    from .persona import apply_reflection, load_or_seed, prompt_block

    home = ns.root / ns.member
    mind = home / "mind"
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    spec = role_for(role)
    persona = load_or_seed(mind, role)

    def system_brief() -> str:
        return (prompt_block(persona) + " Mission: " + str(spec["mission"]) +
                " Only these actions are permitted: " + ", ".join(spec["allow"]) + ".")

    adapter = from_env(system_brief())
    adapter.allowed = frozenset(spec["allow"])
    adapter.default_args = dict(spec.get("args") or {})
    adapter.verbs = set(spec["verbs"])
    adapter.explorer = role == "surveyor"
    from .memory import Memory, WorldMap

    adapter.memory, adapter.world_map = Memory(mind), WorldMap(ns.root)
    adapter.on_turn = lambda pid: (record_self(ns.root, ns.member, pid), cohort_ids(ns.root))[1]
    members = sorted(roles)
    cooldown, offset = stagger(members, ns.member, ns.cooldown, ns.turn_gap)
    print(json.dumps({"member": ns.member, "stagger_offset_s": offset, "cooldown_s": cooldown}), flush=True)
    if stop.wait(offset):
        return 0
    print(json.dumps({"member": ns.member, "role": role, "persona": persona["name"], "persona_version": persona["version"]}), flush=True)
    while not stop.is_set():
        client = NoemaClient(config_home=home, policy=build_policy(role))
        if not getattr(client, "_credential", None):
            print(json.dumps({"member": ns.member, "role": role, "status": "NO_CREDENTIAL"}), flush=True)
            return 3
        try:
            report = client.play(duration=ns.session_seconds, cooldown=cooldown, adapter=adapter)
        except (ConnectionError, EOFError, OSError) as exc:
            print(json.dumps({"member": ns.member, "transport_drop": type(exc).__name__, "retry_in_s": cooldown}), flush=True)
            client.close() if hasattr(client, "close") else None
            stop.wait(cooldown)
            continue
        except Exception as exc:  # websockets.ConnectionClosed* are not OSError subclasses
            if "ConnectionClosed" not in type(exc).__name__:
                raise
            print(json.dumps({"member": ns.member, "transport_drop": type(exc).__name__, "retry_in_s": cooldown}), flush=True)
            stop.wait(cooldown)
            continue
        line = report.as_dict()
        patch = reflect(adapter, persona, adapter.recent)
        persona, accepted = apply_reflection(mind, persona, patch)
        adapter.set_brief(system_brief())
        print(json.dumps({"member": ns.member, "role": role, "actions": len(report),
                          "stop_reason": line.get("stop_reason"), "decisions": dict(adapter.stats),
                          "persona_version": persona["version"], "memories_recalled": adapter.stats_mem, "reflection": "accepted" if accepted else "rejected"},
                         default=str), flush=True)
        stop.wait(ns.cooldown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
