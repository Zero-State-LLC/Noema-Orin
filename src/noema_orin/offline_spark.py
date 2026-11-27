"""T6 (#6): separate offline Spark research Controller target (Noema-Specs ADR-013).

The chamber is a distinct, non-canonical world (`offline.spark.*`) reached only at an
explicit loopback or private-LAN origin. This module validates the target and labels
receipts. It writes no world state and has no fallback to or from the hosted profile:

- hosted credentials (signed JWTs) are refused here, and chamber credentials (opaque
  `spark_` tokens) are refused by the hosted wrappers, which require JWTs;
- hosted origins and hosted world ids are refused here, and `offline.spark.*` worlds are
  refused by `official_isolated.admit_world`;
- receipts carry `evidence_scope=OFFLINE_SPARK_RESEARCH` and `promotable=False`, and
  `assert_not_promotable` rejects any attempt to treat them as hosted or PSR-1 evidence.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

DECISION = "Noema-Specs docs/adr/0013-offline-spark-research-chamber-scope.md"
CHAMBER_PREFIX = "offline.spark."
EVIDENCE_SCOPE = "OFFLINE_SPARK_RESEARCH"
_SUFFIX_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,47}$", re.I)
_TOKEN_RE = re.compile(r"^spark_[A-Za-z0-9_-]{16,256}$")
_HOSTED_HOSTS = ("noema.guru",)
_HOSTED_WORLDS = ("world-01", "world.perihelion", "test.hosted-canonical.")
_ALLOWED_LABELS = frozenset({"OBSERVED", "INFERRED", "SPECULATIVE"})


def admit_chamber_world(world_id: str | None) -> str:
    world = str(world_id or "").strip()
    if any(world.startswith(h) for h in _HOSTED_WORLDS) or not world.startswith(CHAMBER_PREFIX):
        raise ValueError("only offline.spark.<suffix> chamber worlds are admitted")
    suffix = world[len(CHAMBER_PREFIX):]
    if (not suffix or suffix.startswith(".") or suffix.endswith(".") or ".." in suffix
            or not _SUFFIX_RE.match(suffix)):
        raise ValueError("invalid chamber world suffix")
    return world


def admit_chamber_origin(origin: str | None) -> str:
    raw = str(origin or "").strip()
    parsed = urlsplit(raw)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or not parsed.port
            or parsed.username or parsed.password or parsed.path not in {"", "/"}
            or parsed.query or parsed.fragment):
        raise ValueError("chamber origin must be scheme://ip:port")
    host = parsed.hostname
    if any(host == h or host.endswith("." + h) for h in _HOSTED_HOSTS):
        raise ValueError("hosted origin refused for the offline chamber")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("chamber origin must be a literal loopback or private-LAN IP") from exc
    if not (ip.is_loopback or ip.is_private) or ip.is_link_local or ip.is_unspecified:
        raise ValueError("chamber origin must be loopback or private LAN")
    return raw.rstrip("/")


def admit_chamber_token(token: str | None) -> str:
    raw = str(token or "").strip()
    parts = raw.split(".")
    if len(parts) == 3 and all(parts):
        raise ValueError("hosted JWT credentials are refused by the offline chamber")
    if not _TOKEN_RE.match(raw):
        raise ValueError("chamber credential must be an opaque spark_ token")
    return raw


@dataclass(frozen=True)
class OfflineSparkTarget:
    origin: str
    world_id: str
    _token: str

    @classmethod
    def admit(cls, *, origin: str, world_id: str, token: str) -> "OfflineSparkTarget":
        return cls(admit_chamber_origin(origin), admit_chamber_world(world_id),
                   admit_chamber_token(token))

    def __repr__(self) -> str:  # never render the credential
        return f"OfflineSparkTarget(origin={self.origin!r}, world_id={self.world_id!r})"

    def auth_header(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self._token}"}


def research_receipt(target: OfflineSparkTarget, *, status: str, claim_label: str = "OBSERVED",
                     **metrics: object) -> dict[str, object]:
    if claim_label not in _ALLOWED_LABELS:
        raise ValueError("chamber claims are at most OBSERVED")
    record: dict[str, object] = {
        "profile": "offline-spark",
        "evidence_scope": EVIDENCE_SCOPE,
        "promotable": False,
        "decision": DECISION,
        "world_id": target.world_id,
        "status": status,
        "claim_label": claim_label,
    }
    for key, value in metrics.items():
        if key in record or "token" in key.lower() or "auth" in key.lower():
            raise ValueError(f"field not allowed in a research receipt: {key}")
        record[key] = value
    return record


def assert_not_promotable(record: dict[str, object]) -> None:
    """Raise if a chamber record is presented as hosted, STUDY or PSR-1 evidence."""
    if record.get("evidence_scope") == EVIDENCE_SCOPE or record.get("profile") == "offline-spark" \
            or str(record.get("world_id", "")).startswith(CHAMBER_PREFIX):
        raise ValueError("offline Spark research evidence cannot be promoted (ADR-013)")
