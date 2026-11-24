"""Controller token expiry watchdog (slice S9). Reads only the JWT `exp`/`sub` claims, never prints tokens.

Usage: python -m noema_orin.token_watch [--dir ~/.config/noema-orin] [--warn-days 7]
Exit 0 all fresh, 1 something expires within warn-days, 2 something expired or unreadable.
"""

import argparse
import base64
import json
import sys
import time
from pathlib import Path


def claims(token: str) -> dict:
    parts = token.strip().strip('"').split(".")
    if len(parts) != 3:
        return {}
    body = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(body))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def check(directory: Path, warn_days: float, now: float | None = None) -> tuple[int, list[dict]]:
    now = time.time() if now is None else now
    rows, worst = [], 0
    for env in sorted(directory.glob("*.env")):
        values = dict(line.split("=", 1) for line in env.read_text().splitlines() if "=" in line)
        token = values.get("NOEMA_TOKEN")
        if not token:
            continue
        c = claims(token)
        exp = c.get("exp")
        if not isinstance(exp, (int, float)):
            rows.append({"file": env.name, "status": "UNREADABLE"})
            worst = 2
            continue
        days = round((exp - now) / 86400, 1)
        status = "EXPIRED" if days <= 0 else "WARN" if days <= warn_days else "OK"
        worst = max(worst, {"OK": 0, "WARN": 1, "EXPIRED": 2}[status])
        rows.append({"file": env.name, "subject": c.get("player_id") or c.get("sub"), "days_left": days, "status": status})
    return worst, rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", type=Path, default=Path.home() / ".config" / "noema-orin")
    ap.add_argument("--warn-days", type=float, default=7)
    ns = ap.parse_args(argv)
    code, rows = check(ns.dir, ns.warn_days)
    print(json.dumps({"token_watch": rows, "exit": code}))
    return code


if __name__ == "__main__":
    sys.exit(main())
