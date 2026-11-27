"""Read-only, non-identifying Jetson Orin Nano sysfs & INA3221 telemetry collector (T13/#167).

Uses an injectable read-only probe seam (like `preflight.py`). Never reads credentials,
hostnames, serial numbers, or network interfaces. Missing sysfs paths degrade cleanly
to `"NOT_COMPUTABLE"`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

_UNKNOWN = "NOT_COMPUTABLE"
_LIMIT = 4096
_GPU_LOAD_PATHS = (
    "/sys/devices/platform/bus@0/17000000.ga10b/load",
    "/sys/devices/gpu.0/load",
)
_CPU_TEMP_PATH = "/sys/class/thermal/thermal_zone0/temp"
_GPU_TEMP_PATH = "/sys/class/thermal/thermal_zone1/temp"
_INA_VOLT_PATHS = (
    "/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon1/in1_input",
    "/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon0/in1_input",
)
_INA_CURR_PATHS = (
    "/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon1/curr1_input",
    "/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon0/curr1_input",
)


class SysfsProbe(Protocol):
    def read_text(self, path: str) -> str: ...


class LocalSysfsProbe:
    def read_text(self, path: str) -> str:
        with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
            text = fh.read(_LIMIT + 1)
        return text if len(text) <= _LIMIT else ""


def _read_int(probe: SysfsProbe, paths: tuple[str, ...]) -> int | None:
    for p in paths:
        try:
            raw = probe.read_text(p).strip()
            if raw and re.fullmatch(r"-?[0-9]{1,12}", raw):
                return int(raw)
        except Exception:
            continue
    return None


def _parse_mem_avail_mib(probe: SysfsProbe) -> int | None:
    try:
        raw = probe.read_text("/proc/meminfo")
    except Exception:
        return None
    m = re.search(r"^MemAvailable:\s+([0-9]{1,12})\s+kB\s*$", raw, re.MULTILINE)
    if not m:
        return None
    return int(m.group(1)) // 1024


def collect_jetson_telemetry(
    *,
    probe: SysfsProbe | None = None,
    llama_metrics: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Collect a bounded, non-identifying hardware health snapshot."""
    src = probe if probe is not None else LocalSysfsProbe()
    gpu_raw = _read_int(src, _GPU_LOAD_PATHS)
    cpu_t_raw = _read_int(src, (_CPU_TEMP_PATH,))
    gpu_t_raw = _read_int(src, (_GPU_TEMP_PATH,))
    ina_mv = _read_int(src, _INA_VOLT_PATHS)
    ina_ma = _read_int(src, _INA_CURR_PATHS)
    vdd_in_mw = (ina_mv * ina_ma) // 1000 if (ina_mv is not None and ina_ma is not None) else None
    mem_avail = _parse_mem_avail_mib(src)
    lm = llama_metrics or {}
    tps = lm.get("llamacpp:predicted_tokens_seconds")
    kv = lm.get("llamacpp:kv_cache_usage_ratio")
    return {
        "gpu_load_pct": round(gpu_raw / 10.0, 1) if gpu_raw is not None else _UNKNOWN,
        "cpu_temp_c": round(cpu_t_raw / 1000.0, 1) if cpu_t_raw is not None else _UNKNOWN,
        "gpu_temp_c": round(gpu_t_raw / 1000.0, 1) if gpu_t_raw is not None else _UNKNOWN,
        "vdd_in_mw": int(vdd_in_mw) if vdd_in_mw is not None else _UNKNOWN,
        "mem_avail_mib": int(mem_avail) if mem_avail is not None else _UNKNOWN,
        "llama_tps": round(float(tps), 2) if isinstance(tps, (int, float)) else _UNKNOWN,
        "kv_cache_ratio": round(float(kv), 4) if isinstance(kv, (int, float)) else _UNKNOWN,
    }
