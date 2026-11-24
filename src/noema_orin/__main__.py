"""Synthetic, opt-in dry-run CLI. No live client or network path."""

import argparse
import json
import os
import signal
import threading
from pathlib import Path

from typing import NoReturn

from .group import run_group
from .profiles import select
from .receipts import receipt
from .runner import FakeClient, ScriptedAdapter, run


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError("invalid invocation")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject ambiguous JSON keys at every object depth before controller work."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate fixture key")
        result[key] = value
    return result


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description="NOEMA Orin synthetic Controller dry-run", add_help=False)
    parser.add_argument("--profile")
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--group")
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
                fixture = json.loads(args.fixture.read_text(encoding="utf-8"), object_pairs_hook=_unique_object) if args.fixture else None
            except Exception:
                # Fixture input is untrusted; never echo parser or filesystem errors.
                fixture = None
            if args.group is not None:
                return _group(args.group, fixture)
            outcome = run(profile="hosted", fixture=fixture, client=FakeClient(), adapter=ScriptedAdapter())
    print(json.dumps(outcome, sort_keys=True, separators=(",", ":")))
    return 0 if outcome["status"] == "ATTEMPTED" else 1


def _emit(record: dict[str, object]) -> None:
    print(json.dumps(record, sort_keys=True, separators=(",", ":")), flush=True)


def _group(raw_size: str, fixture: object) -> int:
    """Group dry run: one line per member, then one GROUP_SUMMARY line."""
    size: object = int(raw_size) if raw_size.isascii() and raw_size.isdigit() else raw_size
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    # Test-only pacing so the group-stop path can be exercised; not a tuning knob.
    delay_raw = os.environ.get("NOEMA_ORIN_TEST_MEMBER_DELAY", "")
    delay = float(delay_raw) if delay_raw.replace(".", "", 1).isdigit() else 0.0
    pace = (lambda: stop.wait(delay)) if delay else None
    members, summary = run_group(profile="hosted", fixture=fixture, size=size,  # type: ignore[arg-type]
                                 client_factory=lambda m: FakeClient(),
                                 adapter_factory=lambda m: ScriptedAdapter(),
                                 stop=stop, before_member=pace)
    for member in members:
        _emit(member)
    _emit(summary)
    return 0 if summary["group_status"] == "ATTEMPTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
