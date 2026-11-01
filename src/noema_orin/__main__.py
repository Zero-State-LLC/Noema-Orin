"""Synthetic, opt-in dry-run CLI. No live client or network path."""

import argparse
import json
from pathlib import Path

from typing import NoReturn

from .profiles import select
from .receipts import receipt
from .runner import FakeClient, ScriptedAdapter, run


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError("invalid invocation")


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description="NOEMA Orin synthetic Controller dry-run", add_help=False)
    parser.add_argument("--profile")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    try:
        args = parser.parse_args(argv)
    except (ValueError, SystemExit):
        outcome: dict[str, object] = receipt("REFUSED", "INVALID_INVOCATION")
    else:
        refusal = select(args.profile)
        if refusal is not None:
            outcome = receipt("REFUSED", refusal)
        elif not args.dry_run:
            outcome = receipt("REFUSED", "DRY_RUN_REQUIRED", hosted=True)
        else:
            try:
                fixture = json.loads(args.fixture.read_text(encoding="utf-8")) if args.fixture else None
            except Exception:
                # Fixture input is untrusted; never echo parser or filesystem errors.
                fixture = None
            outcome = run(profile="hosted", fixture=fixture, client=FakeClient(), adapter=ScriptedAdapter())
    print(json.dumps(outcome, sort_keys=True, separators=(",", ":")))
    return 0 if outcome["status"] == "ATTEMPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
