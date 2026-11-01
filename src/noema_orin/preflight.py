"""Read-only local host inspection; never a Jetson qualification verdict."""

import importlib.metadata
import json
import platform
import re
import shutil
import sys
from pathlib import Path
from typing import Optional, Protocol

from .receipts import SOURCE_SHA

_UNKNOWN = "NOT_COMPUTABLE"
_LIMIT = 4096
_GIB = 1024 ** 3
_BUCKETS = (4, 8, 16, 32, 64, 128)
_MODEL = "NVIDIA Jetson Orin Nano Developer Kit"
_L4T = re.compile(
    r"# R(\d{2}) \(release\), REVISION: (\d{1,2})\.(\d{1,2})"
    r"(?:, GCID: \d{1,12})?(?:, BOARD: [a-z0-9_-]{1,24})?"
    r"(?:, EABI: aarch64)?(?:, DATE: [A-Za-z0-9 :+/-]{1,48})?"
)
_VERSION = re.compile(r"\d{1,2}\.\d{1,2}\.\d{1,3}")


class HostProbe(Protocol):
    """Read-only observation seam; fake implementations need no inheritance."""

    def read_text(self, path: str) -> str: ...
    def machine(self) -> str: ...
    def python_version(self) -> str: ...
    def free_bytes(self) -> int: ...
    def client_version(self) -> str: ...


class LocalHostProbe:
    """Only bounded local reads and standard-library metadata queries."""

    def read_text(self, path: str) -> str:
        with Path(path).open("r", encoding="utf-8", errors="replace") as stream:
            text = stream.read(_LIMIT + 1)
        return text if len(text) <= _LIMIT else ""

    def machine(self) -> str:
        return platform.machine()

    def python_version(self) -> str:
        return ".".join(str(piece) for piece in sys.version_info[:3])

    def free_bytes(self) -> int:
        return shutil.disk_usage("/").free

    def client_version(self) -> str:
        return importlib.metadata.version("noema-client")


def _observe(call):
    try:
        return call()
    except Exception:
        return None


def _choice(raw, choices):
    return raw if type(raw) is str and raw in choices else _UNKNOWN


def _version(raw):
    return raw if type(raw) is str and _VERSION.fullmatch(raw) else _UNKNOWN


def _os_release(raw):
    if type(raw) is not str or len(raw) > _LIMIT:
        return _UNKNOWN, _UNKNOWN
    fields = {}
    for key in ("ID", "VERSION_ID"):
        values = re.findall(r"^" + key + r"=(?:\"([^\"\n]*)\"|([^\n]*))$", raw, re.MULTILINE)
        if len(values) != 1:
            return _UNKNOWN, _UNKNOWN
        fields[key] = values[0][0] or values[0][1]
    return _choice(fields["ID"], {"ubuntu"}), _choice(fields["VERSION_ID"], {"22.04", "24.04"})


def _l4t(raw):
    if type(raw) is not str or len(raw) > _LIMIT:
        return _UNKNOWN
    match = _L4T.fullmatch(raw.strip())
    if not match:
        return _UNKNOWN
    release, major, minor = match.groups()
    return f"R{release}.{major}.{minor}"


def _bucket(value):
    if type(value) is not int or value < 0 or value > 1024 ** 5:
        return _UNKNOWN
    gib = value // _GIB
    lower = 0
    for upper in _BUCKETS:
        if gib < upper:
            return f"{lower}-{upper}"
        lower = upper
    return "128+"


def _ram(raw):
    if type(raw) is not str or len(raw) > _LIMIT:
        return _UNKNOWN
    values = re.findall(r"^MemTotal:\s*(\d{1,12}) kB\s*$", raw, re.MULTILINE)
    if len(values) != 1:
        return _UNKNOWN
    return _bucket(int(values[0]) * 1024)


def _family(raw, machine):
    if machine not in ("aarch64", "arm64") or type(raw) is not str:
        return _UNKNOWN
    return "JETSON_ORIN_NANO_CANDIDATE" if raw.rstrip("\x00") == _MODEL else _UNKNOWN


def run_preflight(probe: Optional[HostProbe] = None) -> dict[str, str]:
    """Produce a finite, non-identifying local receipt from injected read-only observations."""
    source = probe if probe is not None else LocalHostProbe()
    read = lambda path: _observe(lambda: source.read_text(path))
    os_id, os_version = _os_release(read("/etc/os-release"))
    machine = _choice(_observe(source.machine), {"aarch64", "arm64", "x86_64"})
    return {
        "source_sha": SOURCE_SHA,
        "claim_label": "SPECULATIVE",
        "evidence_scope": "LOCAL_PREFLIGHT_ONLY",
        "machine": machine,
        "os_id": os_id,
        "os_version": os_version,
        "l4t_release": _l4t(read("/etc/nv_tegra_release")),
        "device_family": _family(read("/proc/device-tree/model"), machine),
        "python_version": _version(_observe(source.python_version)),
        "client_version": _version(_observe(source.client_version)),
        "ram_gib_bucket": _ram(read("/proc/meminfo")),
        "storage_free_gib_bucket": _bucket(_observe(source.free_bytes)),
        "jetpack_version": _UNKNOWN,
        "device_metrics": _UNKNOWN,
        "model_load": _UNKNOWN,
        "tokens_per_second": _UNKNOWN,
        "power": _UNKNOWN,
        "command_latency": _UNKNOWN,
    }


def main() -> int:
    print(json.dumps(run_preflight(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
