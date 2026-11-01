"""Credential-free, loopback-only proof of the pinned first-party Controller client.

Not a production adapter or CLI route. Requires noema-client v0.1.23 and Python 3.11+.
"""
from __future__ import annotations

import http.client
import json
import os
import tempfile
from typing import Mapping
from urllib.parse import urlsplit

_SELECTORS = (
    "NOEMA_TOKEN", "NOEMA_SERVER", "NOEMA_CONFIG_DIR", "NOEMA_WORLD_ID",
    "NOEMA_ADMIN_TOKEN", "XDG_CONFIG_HOME",
)


def _loopback_http(origin: str):
    """Use HTTPConnection directly: urllib's redirect/proxy handlers are unsafe here."""
    port = urlsplit(origin).port

    def request(method, url, body=None, token=None, headers=None):
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or parsed.netloc != f"127.0.0.1:{port}"
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("non-loopback client request refused")
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request_headers = {"content-type": "application/json", "accept": "application/json"}
        if token:
            request_headers["authorization"] = f"Bearer {token}"
        if headers:
            request_headers.update({k: v for k, v in headers.items() if v})
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            connection.request(method, parsed.path, body=payload, headers=request_headers)
            response = connection.getresponse()
            raw = response.read()
            result = json.loads(raw) if raw else {}
            if response.status >= 400:
                result["_http_status"] = response.status
            elif response.status >= 300:
                raise ValueError("redirect refused")
            return result
        finally:
            connection.close()

    return request


class OfficialLoopbackClient:
    """Translate the synthetic CommandClient seam into a real client on loopback."""

    def __init__(self, *, server: str, policy: object = None) -> None:
        parsed = urlsplit(server)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
                or not parsed.port or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment
                or parsed.netloc != f"127.0.0.1:{parsed.port}"):
            raise ValueError("loopback HTTP origin with explicit port required")
        if any(os.environ.get(key) for key in _SELECTORS):
            raise ValueError("inherited NOEMA configuration is forbidden in loopback proof")
        from noema_client import NoemaClient, __version__
        if __version__ != "0.1.23":
            raise ValueError("unexpected official client version")
        self.server = server
        # Own the directory: accepting even an empty caller path could redirect
        # fixture credentials through a symlink or into a persistent home.
        self._config = tempfile.TemporaryDirectory(prefix="noema-orin-loopback-")
        try:
            self._client = NoemaClient(server=server, config_home=self._config.name,
                                       transport="http", http=_loopback_http(server), policy=policy)
        except BaseException:
            self._config.cleanup()
            raise
        self.submissions = 0
        self._prepared = False

    def prepare(self) -> None:
        discovery = self._client.discover()
        # The SDK uses the discovered command path after enrollment; refuse
        # a substituted origin or path before a fixture token is issued.
        # FakeNoema publishes http://fixture/v1/command as fixture metadata;
        # the SDK extracts only its path. The injected HTTP transport still
        # enforces the actual destination for every request.
        if discovery.command_uri not in {f"{self.server}/v1/command", "http://fixture/v1/command"}:
            raise ValueError("unexpected loopback command URI")
        # connect(auto_enter=True) already observes after ENTER_WORLD.
        self._client.connect()
        self._prepared = True

    def model_context(self):
        return self._client.model_context()

    def submit(self, proposal: Mapping[str, object]) -> object:
        if not self._prepared:
            raise RuntimeError("local official client not prepared")
        if (type(proposal) is not dict or set(proposal) != {"action", "target_id", "arguments"}
                or proposal["action"] != "LOOK" or proposal["target_id"] is not None
                or type(proposal["arguments"]) is not dict or proposal["arguments"]):
            raise ValueError("invalid local proof proposal")
        from noema_client import ActionProposal
        self.submissions += 1
        result = self._client.act(ActionProposal(action="LOOK", target_id=None, arguments={}))
        if result.ok is not True:
            raise RuntimeError("official client rejected local fake action")
        return result

    def close(self) -> None:
        try:
            self._client.close()
        finally:
            self._config.cleanup()
