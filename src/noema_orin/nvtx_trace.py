"""Zero-overhead optional NVTX markers for NVIDIA Nsight Systems profiling (T14/#168)."""

from __future__ import annotations

import contextlib
import os
from typing import Iterator

_ENABLED = os.environ.get("NOEMA_NVTX", "0") == "1"


@contextlib.contextmanager
def nvtx_range(label: str) -> Iterator[None]:
    """Emit an NVTX range when `NOEMA_NVTX=1` and `nvtx` is installed; otherwise no-op."""
    if not _ENABLED and os.environ.get("NOEMA_NVTX", "0") != "1":
        yield
        return
    try:
        import nvtx  # type: ignore[import-not-found]
    except ImportError:
        yield
        return
    with nvtx.annotate(label):
        yield
