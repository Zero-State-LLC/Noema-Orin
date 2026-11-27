"""Opt-in physical Jetson Orin Nano qualification harness for Issue #5 / G-002 (T14/#168).

Intentionally separate from `preflight.py` (`SPEC-T5A`), which remains untouched as a
read-only `LOCAL_PREFLIGHT_ONLY` / `SPECULATIVE` probe. Emits one allowlisted,
credential-free JSON receipt. Claims `"OBSERVED"` ONLY when physical Jetson Orin Nano
hardware, INA3221 power, and live benchmark metrics are all observed; never fabricates
hardware measurements on non-Jetson hosts.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from typing import Any, Callable

from .embedder import default_embedder
from .jetson_telemetry import SysfsProbe, collect_jetson_telemetry
from .llm_client import call_llama_server, fetch_llama_metrics
from .preflight import _MODELS, run_preflight
from .receipts import SOURCE_SHA

_UNKNOWN = "NOT_COMPUTABLE"
_JETSON_MODELS = set(_MODELS) | {m + "\x00" for m in _MODELS}


def _default_llm_bench(base_url: str, model: str) -> dict[str, Any]:
    t0 = time.monotonic()
    out = call_llama_server(
        base_url=base_url,
        model=model,
        system="Reply with JSON {\"ok\": true}.",
        user="ping",
        max_tokens=24,
        timeout=20.0,
    )
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
    lm = fetch_llama_metrics(base_url)
    if out is None:
        return {}
    return {
        "tokens_per_second": lm.get("llamacpp:predicted_tokens_seconds", _UNKNOWN),
        "prompt_ms": elapsed_ms,
        "model_load_s": _UNKNOWN,
    }


def _default_embed_bench() -> dict[str, Any]:
    emb = default_embedder()
    samples: list[float] = []
    for text in (
        "Civic Exchange barter stall stock power_cell",
        "Relay Quarter damaged relay condition 40",
        "Archive Annex fossilized scar reconstruction",
    ):
        t0 = time.monotonic()
        vec = emb.embed(text)
        dt_ms = (time.monotonic() - t0) * 1000.0
        if vec:
            samples.append(dt_ms)
    if not samples:
        return {}
    samples.sort()
    p95 = samples[min(len(samples) - 1, int(len(samples) * 0.95))]
    return {"embed_p95_ms": round(p95, 2)}


def run_qualification(
    *,
    sysfs_probe: SysfsProbe | None = None,
    device_model: str | None = None,
    l4t_release: str | None = None,
    llm_bench: Callable[[], dict[str, Any]] | None = None,
    embed_bench: Callable[[], dict[str, Any]] | None = None,
    command_bench: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run opt-in qualification checks and return one allowlisted, credential-free receipt."""
    pf = run_preflight()
    model_str = device_model if device_model is not None else ""
    if not model_str:
        try:
            with open("/proc/device-tree/model", "r", encoding="utf-8", errors="replace") as fh:
                model_str = fh.read(256).strip("\x00\n ")
        except OSError:
            model_str = ""
    l4t = l4t_release if l4t_release is not None else pf["l4t_release"]
    is_jetson = model_str in _JETSON_MODELS or pf["device_family"] == "JETSON_ORIN_NANO_CANDIDATE"

    base_url = os.environ.get("NOEMA_LOCAL_LLM_BASE", "http://127.0.0.1:8081/v1")
    llm_model = os.environ.get("NOEMA_LOCAL_LLM_MODEL", "qwen2.5-3b-instruct-q4_k_m")
    lm_metrics = fetch_llama_metrics(base_url) if llm_bench is None else {}
    hw = collect_jetson_telemetry(probe=sysfs_probe, llama_metrics=lm_metrics)

    llm_res = llm_bench() if llm_bench is not None else _default_llm_bench(base_url, llm_model)
    emb_res = embed_bench() if embed_bench is not None else _default_embed_bench()
    cmd_res = command_bench() if command_bench is not None else {}

    tps = llm_res.get("tokens_per_second", _UNKNOWN)
    prompt_ms = llm_res.get("prompt_ms", _UNKNOWN)
    model_load_s = llm_res.get("model_load_s", _UNKNOWN)
    embed_p95_ms = emb_res.get("embed_p95_ms", _UNKNOWN)
    cmd_latency_ms = cmd_res.get("command_latency_ms", _UNKNOWN)
    power_mw = hw.get("vdd_in_mw", _UNKNOWN)

    has_observed_hw = (
        is_jetson
        and l4t != _UNKNOWN
        and isinstance(power_mw, (int, float))
        and isinstance(tps, (int, float))
    )
    return {
        "source_sha": SOURCE_SHA,
        "evidence_scope": "PHYSICAL_ORIN_QUALIFICATION",
        "claim_label": "OBSERVED" if has_observed_hw else "SPECULATIVE",
        "device_family": "JETSON_ORIN_NANO" if is_jetson else _UNKNOWN,
        "l4t_release": l4t,
        "ram_gib_bucket": pf["ram_gib_bucket"],
        "gpu_load_pct": hw.get("gpu_load_pct", _UNKNOWN),
        "cpu_temp_c": hw.get("cpu_temp_c", _UNKNOWN),
        "gpu_temp_c": hw.get("gpu_temp_c", _UNKNOWN),
        "mem_avail_mib": hw.get("mem_avail_mib", _UNKNOWN),
        "power_mw_avg": power_mw,
        "model_load_s": model_load_s,
        "tokens_per_second": tps,
        "prompt_ms": prompt_ms,
        "embed_p95_ms": embed_p95_ms,
        "command_latency_ms": cmd_latency_ms,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Opt-in Jetson Orin Nano physical qualification receipt generator (Issue #5)")
    ap.parse_args(argv)
    print(json.dumps(run_qualification(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
