"""Bounded rotation for the append-only unit logs (`~/noema-players/logs/*.log`).

The Orin has no logrotate, and every unit writes with systemd `StandardOutput=append:`, which keeps
one file descriptor open in O_APPEND mode. Copy-then-truncate is safe for that: the writer's next
append lands at offset 0 of the truncated file, never in a hole. A line written between the copy
and the truncate is lost; at roughly one line per minute per agent that is rare and acceptable for
operator logs. The canonical records (metrics.db, transitions.jsonl) do not live here.

Usage: python -m noema_orin.logrotate [--root DIR] [--max-mb N] [--keep N]
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
from pathlib import Path

DEFAULT_MAX_MB = 8
DEFAULT_KEEP = 5


def rotate(path: Path, *, max_bytes: int, keep: int) -> bool:
    """Rotate `path` to `path.1.gz` (shifting older ones) when it is at least `max_bytes`."""
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        return False
    if size < max_bytes or keep < 1:
        return False
    oldest = path.with_name(f"{path.name}.{keep}.gz")
    if oldest.exists():
        oldest.unlink()
    for n in range(keep - 1, 0, -1):
        src = path.with_name(f"{path.name}.{n}.gz")
        if src.exists():
            src.rename(path.with_name(f"{path.name}.{n + 1}.gz"))
    tmp = path.with_name(f"{path.name}.1.gz.tmp")
    with path.open("rb") as src, gzip.open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst)
    os.chmod(tmp, path.stat().st_mode & 0o777)
    tmp.rename(path.with_name(f"{path.name}.1.gz"))
    with path.open("r+b") as fh:
        fh.truncate(0)
    return True


def rotate_dir(root: Path, *, max_bytes: int, keep: int) -> list[str]:
    return [p.name for p in sorted(Path(root).glob("*.log")) if rotate(p, max_bytes=max_bytes, keep=keep)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="noema_orin.logrotate")
    ap.add_argument("--root", type=Path, default=Path.home() / "noema-players" / "logs")
    ap.add_argument("--max-mb", type=float, default=DEFAULT_MAX_MB)
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP)
    args = ap.parse_args(argv)
    rotated = rotate_dir(args.root, max_bytes=int(args.max_mb * 1024 * 1024), keep=args.keep)
    print(json.dumps({"logrotate": rotated, "max_mb": args.max_mb, "keep": args.keep}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
