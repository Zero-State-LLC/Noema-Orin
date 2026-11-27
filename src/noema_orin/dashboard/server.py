"""Stdlib HTTP + Server-Sent Events (SSE) server for Noema-Orin Mission Control (D2/#182).

Zero third-party dependencies, loopback-default (`127.0.0.1:8787`), dual-scope auth
(read token vs. operator control token), and real-time SSE turn/hardware streaming.
"""

from __future__ import annotations

import hmac
import json
import mimetypes
import os
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .controls import DashboardController
from .state import DashboardStateReader

STATIC_DIR = Path(__file__).resolve().parent / "static"
_MAX_BODY_BYTES = 16_384


def _token_matches(provided: str, expected: str) -> bool:
    if not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def create_dashboard_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8787,
    reader: DashboardStateReader,
    controller: DashboardController,
    read_token: str | None = None,
    control_token: str | None = None,
    allow_local_kiosk_control: bool = False,
) -> ThreadingHTTPServer:
    """Create a configured ThreadingHTTPServer for the Noema-Orin dashboard."""
    read_tok = (read_token or "").strip()
    ctrl_tok = (control_token or "").strip()
    local_kiosk = bool(allow_local_kiosk_control and host in ("127.0.0.1", "localhost", "::1"))

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _extract_token(self, query: dict[str, list[str]]) -> str:
            auth = self.headers.get("Authorization") or ""
            if auth.lower().startswith("bearer "):
                return auth[7:].strip()
            cookie = self.headers.get("Cookie") or ""
            for part in cookie.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    if k == "noema_dash_token":
                        return v.strip()
            if query.get("token"):
                return str(query["token"][0]).strip()
            return ""

        def _is_loopback_client(self) -> bool:
            ip = str(self.client_address[0] if self.client_address else "")
            return ip in ("127.0.0.1", "::1")

        def _check_read(self, query: dict[str, list[str]]) -> bool:
            if not read_tok and not ctrl_tok:
                return self._is_loopback_client()
            tok = self._extract_token(query)
            if not tok:
                return False
            return _token_matches(tok, read_tok) or _token_matches(tok, ctrl_tok)

        def _check_control(self, query: dict[str, list[str]]) -> tuple[bool, int]:
            if local_kiosk and not ctrl_tok and self._is_loopback_client():
                return True, 200
            tok = self._extract_token(query)
            if not tok:
                return False, 401
            if ctrl_tok and _token_matches(tok, ctrl_tok):
                return True, 200
            if read_tok and _token_matches(tok, read_tok):
                return False, 403
            return False, 401

        def _send_json(self, code: int, payload: Any) -> None:
            raw = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _send_static(self, rel: str) -> None:
            safe = Path(rel.lstrip("/"))
            root_dir = STATIC_DIR.resolve()
            target = (root_dir / safe).resolve()
            if not target.is_relative_to(root_dir) or not target.is_file():
                self._send_json(404, {"error": "not found"})
                return
            data = target.read_bytes()
            ctype, _ = mimetypes.guess_type(target.name)
            self.send_response(200)
            self.send_header("Content-Type", (ctype or "application/octet-stream") + "; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json_body(self) -> dict[str, Any] | None:
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                return None
            if length < 0 or length > _MAX_BODY_BYTES:
                return None
            raw = self.rfile.read(length) if length else b"{}"
            try:
                obj = json.loads(raw.decode("utf-8"))
            except ValueError:
                return None
            return obj if isinstance(obj, dict) else None

        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)

            if path in ("/", "/index.html"):
                self._send_static("index.html")
                return
            if path.startswith("/static/"):
                self._send_static(path.removeprefix("/static/"))
                return

            if path == "/api/health":
                self._send_json(200, {"ok": True, "ts": round(time.time(), 2)})
                return

            if not self._check_read(query):
                self._send_json(401, {"error": "unauthorized"})
                return

            if path == "/api/snapshot":
                self._send_json(200, reader.cached_snapshot())
                return

            if path == "/api/map":
                snap = reader.cached_snapshot()
                self._send_json(200, {"map_sig": snap.get("map_sig"), "map": snap.get("map")})
                return

            if path.startswith("/api/agent/"):
                member = path.removeprefix("/api/agent/").strip("/")
                q = str((query.get("q") or [""])[0])
                try:
                    self._send_json(200, reader.agent_detail(member, query=q))
                except ValueError:
                    self._send_json(404, {"error": "unknown member"})
                return

            if path == "/api/stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                last_snap = 0.0
                offsets: dict[str, int] = {}
                sent_map_sig = None
                try:
                    interval = max(2.0, min(30.0, float((query.get("interval") or ["4"])[0])))
                except ValueError:
                    interval = 4.0
                try:
                    while True:
                        now = time.monotonic()
                        for ev in reader.poll_new_turns(offsets):
                            frame = f"event: {ev['event']}\ndata: {json.dumps(ev, default=str)}\n\n"
                            self.wfile.write(frame.encode("utf-8"))
                        if now - last_snap >= interval:
                            snap = reader.cached_snapshot()
                            # Delta frame: the map (about half the payload) only when it changed, and no
                            # recent_turns (the turn events already carry them).
                            slim = {k: v for k, v in snap.items() if k not in ("map", "recent_turns")}
                            if snap.get("map_sig") != sent_map_sig:
                                slim["map"] = snap.get("map")
                                sent_map_sig = snap.get("map_sig")
                            frame = f"event: snapshot\ndata: {json.dumps(slim, default=str)}\n\n"
                            self.wfile.write(frame.encode("utf-8"))
                            last_snap = now
                        else:
                            self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                        time.sleep(1.5)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return

            self._send_json(404, {"error": "not found"})

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)
            ok_auth, status_code = self._check_control(query)
            if not ok_auth:
                self._send_json(status_code, {"error": "forbidden" if status_code == 403 else "unauthorized"})
                return
            body = self._read_json_body()
            if body is None:
                self._send_json(400, {"error": "invalid json body"})
                return

            if path == "/api/control/unit":
                ok, res = controller.unit_control(str(body.get("unit") or ""), str(body.get("action") or ""))
                self._send_json(200 if ok else 400, res)
                return
            if path == "/api/control/group":
                ok, res = controller.group_control(str(body.get("action") or ""), str(body.get("preset") or "full"))
                self._send_json(200 if ok else 400, res)
                return
            if path.startswith("/api/control/knobs/"):
                member = path.removeprefix("/api/control/knobs/").strip("/")
                ok, res = controller.update_knobs(member, body)
                self._send_json(200 if ok else 400, res)
                return
            if path.startswith("/api/control/rsi/"):
                member = path.removeprefix("/api/control/rsi/").strip("/")
                ok, res = controller.rsi_control(member, str(body.get("action") or ""))
                self._send_json(200 if ok else 400, res)
                return
            if path == "/api/control/mode":
                ok, res = controller.set_runtime_mode(
                    str(body.get("inference_mode") or ""),
                    bool(body.get("grounded_voice", False)),
                )
                self._send_json(200 if ok else 400, res)
                return
            if path == "/api/control/claims/release":
                ok, res = controller.release_claim(str(body.get("target_id") or ""))
                self._send_json(200 if ok else 400, res)
                return
            if path.startswith("/api/control/agenda/"):
                member = path.removeprefix("/api/control/agenda/").strip("/")
                ok, res = controller.refresh_agenda(member)
                self._send_json(200 if ok else 400, res)
                return
            if path == "/api/control/ops":
                ok, res = controller.run_ops(str(body.get("job") or ""))
                self._send_json(200 if ok else 400, res)
                return
            self._send_json(404, {"error": "not found"})

    return ThreadingHTTPServer((host, int(port)), Handler)
