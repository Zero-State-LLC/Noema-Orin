"""Synthetic, opt-in dry-run CLI. No live client or network path."""

import argparse
import json
from pathlib import Path

from .runner import FakeClient, ScriptedAdapter, run


def main() -> int:
    parser = argparse.ArgumentParser(description="NOEMA Orin synthetic Controller dry-run")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    outcome = run(profile=args.profile, fixture=fixture, client=FakeClient(), adapter=ScriptedAdapter())
    print(json.dumps(outcome, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
