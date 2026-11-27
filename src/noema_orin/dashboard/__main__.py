"""CLI entrypoint for `python3 -m noema_orin.dashboard` (D-077)."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
from pathlib import Path

from .controls import DashboardController, LiveSystemdRunner
from .server import create_dashboard_server
from .state import DashboardStateReader


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="NOEMA Orin Native Always-On Mission Control Dashboard")
    ap.add_argument("--host", default=os.environ.get("NOEMA_DASHBOARD_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("NOEMA_DASHBOARD_PORT", "8787")))
    ap.add_argument("--root", type=Path, default=Path(os.environ.get("NOEMA_PLAYERS_ROOT", str(Path.home() / "noema-players"))))
    ap.add_argument("--config-dir", type=Path, default=Path(os.environ.get("NOEMA_ORIN_CONFIG_DIR", str(Path.home() / ".config" / "noema-orin"))))
    ns = ap.parse_args(argv)

    runner = LiveSystemdRunner()
    reader = DashboardStateReader(root=ns.root, config_dir=ns.config_dir, systemd_runner=runner)
    controller = DashboardController(root=ns.root, config_dir=ns.config_dir, systemd_runner=runner)
    allow_kiosk_ctrl = os.environ.get("NOEMA_DASHBOARD_ALLOW_LOCAL_CONTROL", "1") == "1"

    srv = create_dashboard_server(
        host=ns.host,
        port=ns.port,
        reader=reader,
        controller=controller,
        read_token=os.environ.get("NOEMA_DASHBOARD_READ_TOKEN"),
        control_token=os.environ.get("NOEMA_DASHBOARD_CONTROL_TOKEN"),
        allow_local_kiosk_control=allow_kiosk_ctrl,
    )

    def _stop(*_args):
        srv.shutdown()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    print(json.dumps({"dashboard": "listening", "host": ns.host, "port": ns.port, "root": str(ns.root)}), flush=True)
    try:
        srv.serve_forever(poll_interval=0.5)
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
