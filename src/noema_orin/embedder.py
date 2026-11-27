"""Pluggable TensorRT FP16 semantic embedder and stdlib float16 vector math (T12/#166).

On Jetson Orin Nano, all 6 agents share a single local `bge-small-en-v1.5` TensorRT FP16
embedding daemon (~80 MiB GPU footprint, <3 ms/query) over loopback HTTP. On non-Jetson
CI hosts, `NullEmbedder` preserves pure FTS5 retrieval with zero extra dependencies.
"""

from __future__ import annotations

import json
import math
import os
import struct
import urllib.request
from typing import Protocol


class Embedder(Protocol):
    model_name: str
    dim: int

    def embed(self, text: str) -> list[float] | None: ...


class NullEmbedder:
    """No-op embedder used on CI and hosts without a local TensorRT embedder daemon."""

    model_name = "none"
    dim = 0

    def embed(self, text: str) -> list[float] | None:
        return None


class HttpTrtEmbedder:
    """Thin loopback client to the shared Jetson TensorRT FP16 `bge-small-en-v1.5` service."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8082",
        *,
        model_name: str = "BAAI/bge-small-en-v1.5-fp16",
        dim: int = 384,
        timeout: float = 1.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.dim = dim
        self.timeout = timeout

    def embed(self, text: str) -> list[float] | None:
        clean = " ".join(str(text or "").split())[:512]
        if not clean:
            return None
        openai = self.base_url.endswith("/v1")
        req = urllib.request.Request(
            self.base_url + ("/embeddings" if openai else "/embed"),
            data=json.dumps({"input": clean, "model": self.model_name}).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        vec = data.get("embedding") if isinstance(data, dict) else None
        if vec is None and openai and isinstance(data, dict):
            # OpenAI shape from llama-server --embedding: {"data": [{"embedding": [...]}]}
            rows = data.get("data")
            if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                vec = rows[0].get("embedding")
        if not isinstance(vec, list) or not vec:
            return None
        try:
            return [float(x) for x in vec]
        except (TypeError, ValueError):
            return None


def default_embedder() -> Embedder:
    url = os.environ.get("NOEMA_TRT_EMBED_URL", "").strip()
    if url:
        return HttpTrtEmbedder(base_url=url)
    return NullEmbedder()


def pack_f16(vec: list[float]) -> bytes:
    """Pack a float vector into compact little-endian IEEE 754 float16 bytes (768 B for 384-dim)."""
    return struct.pack(f"<{len(vec)}e", *(float(x) for x in vec))


def unpack_f16(blob: bytes) -> list[float]:
    if not blob or len(blob) % 2 != 0:
        return []
    count = len(blob) // 2
    return list(struct.unpack(f"<{count}e", blob))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (na * nb)))
