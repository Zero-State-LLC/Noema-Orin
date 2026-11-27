"""T4 (#4): wrap the pinned official client for an admitted isolated hosted world.

Wraps `noema_client.NoemaClient(isolated=True)`; it does not fork it or add a Player
class. Only `test.hosted-canonical.<suffix>` worlds are admitted and Perihelion is
refused, mirroring `noema_client.isolated`. Credentials come from the caller (an
Admin-minted controller token and a signed Admin JWT), are held only in memory and a
temporary config home, and never enter the model context or a receipt.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

ISOLATED_PREFIX = "test.hosted-canonical."
_SUFFIX_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,47}$", re.I)
SUPPORTED_CLIENT_VERSIONS = frozenset({"0.2.0"})
HOSTED_SERVER = "https://noema.guru"


def admit_world(world_id: str | None) -> str:
    world = str(world_id or "").strip()
    if not world.startswith(ISOLATED_PREFIX) or "perihelion" in world.lower():
        raise ValueError("only test.hosted-canonical.<suffix> worlds are admitted")
    suffix = world[len(ISOLATED_PREFIX):]
    if (not suffix or suffix.startswith(".") or suffix.endswith(".") or ".." in suffix
            or not _SUFFIX_RE.match(suffix)):
        raise ValueError("invalid isolated world suffix")
    return world


def _looks_like_jwt(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 3 and all(parts)


def _validate_proposal(proposal: Mapping[str, object]) -> None:
    if (type(proposal) is not dict or set(proposal) != {"action", "target_id", "arguments"}
            or proposal["action"] != "LOOK" or proposal["target_id"] is not None
            or type(proposal["arguments"]) is not dict or proposal["arguments"]):
        raise ValueError("invalid isolated proposal")


class OfficialIsolatedClient:
    """CommandClient seam (`prepare`/`model_context`/`submit`/`close`) over the real client."""

    def __init__(self, *, world_id: str, controller_token: str, admin_jwt: str,
                 server: str = HOSTED_SERVER,
                 client_factory: Callable[..., Any] | None = None,
                 client_version: str | None = None,
                 credential_writer: Callable[[str], Any] | None = None,
                 proposal_type: Callable[..., Any] | None = None) -> None:
        self.world_id = admit_world(world_id)
        if server.rstrip("/") != HOSTED_SERVER:
            raise ValueError("isolated attach targets the hosted origin only")
        if not _looks_like_jwt(admin_jwt or ""):
            raise ValueError("signed Admin JWT required")
        if not _looks_like_jwt(controller_token or ""):
            raise ValueError("Admin-minted controller token required")
        if client_factory is None:
            import noema_client
            from noema_client import ActionProposal, NoemaClient
            from noema_client.config import StoredCredential, save_credential
            client_factory, client_version = NoemaClient, noema_client.__version__
            proposal_type = ActionProposal
            credential_writer = lambda home: save_credential(  # noqa: E731
                StoredCredential(access_token=controller_token, server=server), Path(home))
        if client_version not in SUPPORTED_CLIENT_VERSIONS:
            raise ValueError("unexpected official client version")
        self.client_version = client_version
        self._proposal_type = proposal_type or dict
        self._secrets = (admin_jwt, controller_token)
        self._config = tempfile.TemporaryDirectory(prefix="noema-orin-isolated-")
        try:
            # A stored Admin-minted credential means connect() never starts device
            # enrollment (D-010/D-011 system-actor pattern).
            if credential_writer is not None:
                credential_writer(self._config.name)
            self._client = client_factory(
                server, config_home=Path(self._config.name), transport="http", isolated=True,
                world_id=self.world_id, admin_token=admin_jwt)
        except BaseException:
            self._config.cleanup()
            raise
        self._prepared = False
        self.submissions = 0

    def prepare(self) -> None:
        # connect() with a stored credential skips device enrollment and enters the world.
        self._client.connect(auto_enter=True)
        self._prepared = True

    def model_context(self) -> Any:
        ctx = self._client.model_context()
        blob = json.dumps(ctx, default=str)
        if any(secret and secret in blob for secret in self._secrets):
            raise RuntimeError("credential leaked into model context")
        return ctx

    def submit(self, proposal: Mapping[str, object]) -> object:
        if not self._prepared:
            raise RuntimeError("isolated official client not prepared")
        _validate_proposal(proposal)
        self.submissions += 1
        result = self._client.act(self._proposal_type(action="LOOK", target_id=None, arguments={}))
        if getattr(result, "ok", None) is not True:
            raise RuntimeError("official client rejected isolated action")
        return result

    def close(self) -> None:
        try:
            self._client.close()
        finally:
            self._config.cleanup()
            self._secrets = ("", "")
