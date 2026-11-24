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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Persistent Orin civic Player")
    ap.add_argument("--member", required=True)
    ap.add_argument("--root", type=Path, default=Path.home() / "noema-players")
    ap.add_argument("--session-seconds", type=float, default=1800)
    ap.add_argument("--cooldown", type=float, default=20)
    ns = ap.parse_args(argv)
    roles = dict(line.split("\t") for line in (ns.root / "roles.tsv").read_text().split("\n") if "\t" in line)
    role = roles.get(ns.member)
    role_for(role)
    from noema_client.adapters.openai_compatible import OpenAICompatibleAdapter
    from noema_client.client import NoemaClient

    home = ns.root / ns.member
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    adapter = OpenAICompatibleAdapter(base_url=os.environ.get("NOEMA_LLM_BASE", "http://127.0.0.1:11434/v1"),
                                      model=os.environ.get("NOEMA_LLM_MODEL", "qwen2.5:3b"))
    while not stop.is_set():
        client = NoemaClient(config_home=home, policy=build_policy(role))
        if not getattr(client, "_credential", None):
            print(json.dumps({"member": ns.member, "role": role, "status": "NO_CREDENTIAL"}), flush=True)
            return 3
        report = client.play(duration=ns.session_seconds, cooldown=ns.cooldown, adapter=adapter)
        line = report.as_dict()
        print(json.dumps({"member": ns.member, "role": role, "actions": len(report),
                          "stop_reason": line.get("stop_reason")}, default=str), flush=True)
        stop.wait(ns.cooldown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
