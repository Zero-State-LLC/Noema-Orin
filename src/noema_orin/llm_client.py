"""Local CUDA llama-server client with grammar-constrained JSON schemas (T10/#164).

Stdlib-only HTTP client targeting a single shared Jetson Orin Nano `llama-server`
instance (`127.0.0.1:8081/v1`) with dynamic `json_schema` decoding and KV prefix reuse.
"""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any


def build_choice_schema(num_options: int) -> dict[str, Any]:
    """Build a strict JSON schema constraining `choice` to valid menu indices `0..N-1`."""
    count = max(1, int(num_options))
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "noema_menu_choice",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "choice": {"type": "integer", "enum": list(range(count))},
                    "why": {"type": "string", "maxLength": 80},
                },
                "required": ["choice", "why"],
                "additionalProperties": False,
            },
        },
    }


def build_voice_schema(valid_seqs: list[int] | tuple[int, ...]) -> dict[str, Any]:
    """Build a strict JSON schema constraining grounded voice utterances and cited sequence numbers."""
    seqs = sorted({int(s) for s in valid_seqs if isinstance(s, int) and s > 0})
    seq_items: dict[str, Any] = {"type": "integer"}
    if seqs:
        seq_items["enum"] = seqs
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "noema_grounded_utterance",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "utterance": {"type": "string", "maxLength": 280},
                    "cited_seqs": {"type": "array", "items": seq_items, "maxItems": 4},
                },
                "required": ["utterance", "cited_seqs"],
                "additionalProperties": False,
            },
        },
    }


def call_llama_server(
    *,
    base_url: str,
    model: str,
    system: str,
    user: str,
    response_format: dict[str, Any] | None = None,
    max_tokens: int = 80,
    temperature: float = 0.3,
    timeout: float = 15.0,
) -> dict[str, Any] | None:
    """Call OpenAI-compatible local `llama-server` `/v1/chat/completions` with constrained JSON output."""
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = (endpoint if endpoint.endswith("/v1") else endpoint + "/v1") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "temperature": float(temperature),
        "max_tokens": max(16, int(max_tokens)),
        "cache_prompt": True,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if response_format is not None:
        payload["response_format"] = response_format
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    choices = raw.get("choices") if isinstance(raw, dict) else None
    if not isinstance(choices, list) or not choices:
        return None
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    text = str((msg or {}).get("content") or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text[text.find("{") : text.rfind("}") + 1] or "{}")
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) and parsed else None


_PROM_LINE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{[^}]*\})?\s+([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)$")


def fetch_llama_metrics(base_url: str, *, timeout: float = 3.0) -> dict[str, float]:
    """Read Prometheus `/metrics` from local `llama-server` for hardware telemetry (T13/T14)."""
    root = base_url.rstrip("/").removesuffix("/v1")
    req = urllib.request.Request(root + "/metrics", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return {}
    metrics: dict[str, float] = {}
    for line in text.splitlines():
        m = _PROM_LINE.match(line.strip())
        if not m:
            continue
        name, val = m.group(1), float(m.group(2))
        if name in (
            "llamacpp:predicted_tokens_seconds",
            "llamacpp:prompt_tokens_seconds",
            "llamacpp:kv_cache_usage_ratio",
            "llamacpp:requests_processing",
            "llamacpp:n_decode_total",
            "llamacpp:tokens_predicted_total",
        ):
            metrics[name] = round(val, 4)
    return metrics
