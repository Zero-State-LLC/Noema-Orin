"""Resilient websocket factory for the official client (slice S4).

noema-client's WebSocketGateway retries and reconnects on ConnectionError/OSError, but
websockets' ConnectionClosed* is neither, so a dropped socket escaped `play()` and cost
the whole session. This factory (passed as NoemaClient(ws_connect=...)) keeps the
socket alive with pings and re-raises ConnectionClosed as ConnectionError, so the
client's own reconnect-and-retry path handles it. No protocol changes.
"""

from typing import Any


class _Socket:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def _guard(self, fn, *a, **kw):
        from websockets.exceptions import ConnectionClosed

        try:
            return fn(*a, **kw)
        except ConnectionClosed as exc:
            raise ConnectionError(f"websocket closed: {type(exc).__name__}") from exc

    def send(self, data):
        return self._guard(self._inner.send, data)

    def recv(self, *a, **kw):
        return self._guard(self._inner.recv, *a, **kw)

    def close(self, *a, **kw):
        try:
            return self._inner.close(*a, **kw)
        except Exception:
            return None

    def __getattr__(self, name):
        return getattr(self._inner, name)


def connect(url: str, **_: Any) -> _Socket:
    from websockets.sync.client import connect as ws_connect

    return _Socket(ws_connect(url, open_timeout=15, close_timeout=5, ping_interval=20, ping_timeout=20))
