#!/usr/bin/env python3
"""Re-mint Orin controller tokens (slice S9). Operator Mac only; needs a fresh Admin session.

  1. python3 ~/.config/noema-orin/admin_login.py      # writes ~/.config/noema-orin/admin.jwt (1h)
  2. python3 deploy/remint-tokens.py                   # dry run: shows member -> handle, no network
  3. python3 deploy/remint-tokens.py --apply           # mints 30-day tokens, writes *.env 0600, copies to Orin
  4. ssh orin ~/noema-orin-src/deploy/rolling-restart.sh --apply

Handles come from the current token's `sub` (player.<handle>), so identities never change.
Tokens are never printed.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

CONF = Path.home() / ".config" / "noema-orin"
SERVER = "https://noema.guru"


def handle_of(env: Path) -> str | None:
    values = dict(line.split("=", 1) for line in env.read_text().splitlines() if "=" in line)
    parts = values.get("NOEMA_TOKEN", "").strip().split(".")
    if len(parts) != 3:
        return None
    data = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
    sub = data.get("player_id") or data.get("sub") or ""
    return sub.removeprefix("player.") or None


def mint(admin_jwt: str, handle: str, days: int) -> str:
    req = urllib.request.Request(SERVER + "/v1/admin/controller-token", method="POST",
                                 data=json.dumps({"handle": handle, "controller_type": "agent",
                                                  "expires_in": days * 86400}).encode(),
                                 headers={"authorization": f"Bearer {admin_jwt}", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        token = json.loads(resp.read().decode()).get("access_token")
    if not token:
        raise RuntimeError(f"no access_token for {handle}")
    return token


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--only", nargs="*", help="env names, e.g. m01 maint")
    ap.add_argument("--host", default="orin")
    ns = ap.parse_args()
    envs = [p for p in sorted(CONF.glob("*.env")) if p.stem != "memory-sync" and (not ns.only or p.stem in ns.only)]
    plan = [(p, handle_of(p)) for p in envs]
    for p, h in plan:
        print(f"{'mint' if ns.apply else 'would mint'} {p.stem} -> player.{h} ({ns.days}d)")
    if not ns.apply:
        return 0
    admin_jwt = (CONF / "admin.jwt").read_text().strip()
    for p, h in plan:
        if not h:
            print(f"skip {p.stem}: no current handle", file=sys.stderr)
            continue
        token = mint(admin_jwt, h, ns.days)
        lines = [line for line in p.read_text().splitlines() if not line.startswith("NOEMA_TOKEN=")]
        tmp = p.with_suffix(".env.tmp")
        tmp.write_text("\n".join([f"NOEMA_TOKEN={token}"] + lines) + "\n")
        os.chmod(tmp, 0o600)
        tmp.replace(p)
        subprocess.run(["scp", "-q", "-p", str(p), f"{ns.host}:.config/noema-orin/{p.name}"], check=True)
        print(f"minted {p.stem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
