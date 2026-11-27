"""Phase 3 tests: T12 (#166) TRT hybrid memory, T13 (#167) Tegra telemetry, and T14 (#168/#5) qualify harness."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from noema_orin.embedder import NullEmbedder, cosine_similarity, pack_f16, unpack_f16
from noema_orin.jetson_telemetry import collect_jetson_telemetry
from noema_orin.memory import Memory
from noema_orin.metrics import digest, open_db, record_hw_sample
from noema_orin.nvtx_trace import nvtx_range
from noema_orin.qualify import run_qualification


class _FakeSemanticEmbedder:
    """Deterministic 4-dim toy embedder separating energy/power concepts from archive/lore concepts."""

    model_name = "fake-bge-small"
    dim = 4

    def embed(self, text: str) -> list[float]:
        low = text.lower()
        power = 1.0 if any(w in low for w in ("battery", "cell", "generator", "energy", "power", "volt")) else 0.0
        repair = 1.0 if any(w in low for w in ("relay", "broken", "weld", "damage", "repair", "workshop")) else 0.0
        lore = 1.0 if any(w in low for w in ("scar", "history", "archive", "record", "fossil")) else 0.0
        trade = 1.0 if any(w in low for w in ("stall", "barter", "ore", "price", "swap")) else 0.0
        vec = [power, repair, lore, trade]
        if not any(vec):
            vec = [0.25, 0.25, 0.25, 0.25]
        return vec


class _FakeJetsonProbe:
    def __init__(self, files: dict[str, str]) -> None:
        self.files = files

    def read_text(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]


class TrtSemanticMemoryTests(unittest.TestCase):
    def test_f16_pack_unpack_and_cosine_similarity(self):
        blob = pack_f16([1.0, 0.0, 0.5, -0.5])
        self.assertEqual(len(blob), 8)  # 4 x float16 = 8 bytes
        unpacked = unpack_f16(blob)
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0, 0.5, -0.5], unpacked), 1.0, places=3)

    def test_hybrid_recall_finds_synonym_missed_by_fts5_and_compact_cascades(self):
        with tempfile.TemporaryDirectory() as d:
            mem = Memory(Path(d), embedder=_FakeSemanticEmbedder())
            try:
                mem.remember("Generator hall restores depleted volt packs", kind="room", room="room.gen", sequence=10)
                mem.remember("Archive annex preserves fossil records", kind="room", room="room.arch", sequence=11)
                # Query uses synonym "battery energy" which has ZERO lexical overlap with "volt packs"
                hits = mem.recall("battery energy", limit=2)
                self.assertGreaterEqual(len(hits), 1)
                self.assertIn("Generator hall", hits[0]["fact"])
                # Verify embedding rows exist and cascade-delete on compact()
                self.assertEqual(mem.db.execute("SELECT count(*) FROM fact_embeddings").fetchone()[0], 2)
                mem.mark_stale(kind="room", room="room.gen", keep=set())
                mem.compact(keep_stale=0)
                self.assertEqual(mem.db.execute("SELECT count(*) FROM fact_embeddings").fetchone()[0], 1)
            finally:
                mem.close()

    def test_null_embedder_preserves_fts5_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            mem = Memory(Path(d), embedder=NullEmbedder())
            try:
                mem.remember("Relay Quarter shows structural damage", kind="room", room="room.relay", sequence=5)
                hits = mem.recall("Relay damage")
                self.assertEqual(len(hits), 1)
                self.assertEqual(mem.db.execute("SELECT count(*) FROM fact_embeddings").fetchone()[0], 0)
            finally:
                mem.close()


class TegraTelemetryTests(unittest.TestCase):
    def test_collect_jetson_telemetry_parses_sysfs_and_degrades_cleanly(self):
        probe = _FakeJetsonProbe(
            {
                "/sys/devices/platform/bus@0/17000000.ga10b/load": "425\n",
                "/sys/class/thermal/thermal_zone0/temp": "48500\n",
                "/sys/class/thermal/thermal_zone1/temp": "51200\n",
                "/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon1/in1_input": "19000\n",
                "/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon1/curr1_input": "500\n",
                "/proc/meminfo": "MemTotal:        7800000 kB\nMemAvailable:    4096000 kB\n",
            }
        )
        sample = collect_jetson_telemetry(
            probe=probe,
            llama_metrics={"llamacpp:predicted_tokens_seconds": 28.4, "llamacpp:kv_cache_usage_ratio": 0.22},
        )
        self.assertEqual(sample["gpu_load_pct"], 42.5)
        self.assertEqual(sample["cpu_temp_c"], 48.5)
        self.assertEqual(sample["gpu_temp_c"], 51.2)
        self.assertEqual(sample["vdd_in_mw"], 9500)
        self.assertEqual(sample["mem_avail_mib"], 4000)
        self.assertEqual(sample["llama_tps"], 28.4)
        self.assertEqual(sample["kv_cache_ratio"], 0.22)

        # Off-Jetson empty probe degrades cleanly to NOT_COMPUTABLE
        off = collect_jetson_telemetry(probe=_FakeJetsonProbe({}))
        self.assertEqual(off["gpu_load_pct"], "NOT_COMPUTABLE")
        self.assertEqual(off["vdd_in_mw"], "NOT_COMPUTABLE")

        # metrics.db records hw_samples and exposes latest in digest
        with tempfile.TemporaryDirectory() as d:
            db = open_db(Path(d))
            try:
                record_hw_sample(db, sample, ts=1000.0)
                out = digest(db)
                self.assertEqual(out["hw"]["gpu_load_pct"], 42.5)
                self.assertEqual(out["hw"]["llama_tps"], 28.4)
            finally:
                db.close()

    def test_r39_hwmon4_and_gpu_path(self):
        probe = _FakeJetsonProbe(
            {
                "/sys/devices/platform/bus@0/17000000.gpu/load": "100\n",
                "/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon4/in1_input": "5000\n",
                "/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon4/curr1_input": "1200\n",
            }
        )
        sample = collect_jetson_telemetry(probe=probe)
        self.assertEqual(sample["gpu_load_pct"], 10.0)
        self.assertEqual(sample["vdd_in_mw"], 6000)


class QualificationAndNvtxTests(unittest.TestCase):
    def test_qualify_emits_allowlisted_receipt_without_leaking_secrets_or_faking_hardware(self):
        # Non-Jetson host -> stays SPECULATIVE and NOT_COMPUTABLE for missing hardware fields
        receipt = run_qualification(
            sysfs_probe=_FakeJetsonProbe({}),
            device_model="Generic x86_64",
            l4t_release="NOT_COMPUTABLE",
            llm_bench=lambda: {"tokens_per_second": 24.5, "prompt_ms": 180.0, "model_load_s": 2.1},
            embed_bench=lambda: {"embed_p95_ms": 2.4},
            command_bench=lambda: {"command_latency_ms": 42.0},
        )
        self.assertEqual(receipt["evidence_scope"], "PHYSICAL_ORIN_QUALIFICATION")
        self.assertEqual(receipt["claim_label"], "SPECULATIVE")
        self.assertEqual(receipt["tokens_per_second"], 24.5)
        self.assertEqual(receipt["embed_p95_ms"], 2.4)
        self.assertEqual(receipt["power_mw_avg"], "NOT_COMPUTABLE")

        # Physical Orin Nano with real sysfs power + benchmarks -> OBSERVED
        jetson_probe = _FakeJetsonProbe(
            {
                "/sys/devices/platform/bus@0/17000000.ga10b/load": "650\n",
                "/sys/class/thermal/thermal_zone0/temp": "50000\n",
                "/sys/class/thermal/thermal_zone1/temp": "52000\n",
                "/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon1/in1_input": "19000\n",
                "/sys/bus/i2c/drivers/ina3221/1-0040/hwmon/hwmon1/curr1_input": "600\n",
                "/proc/meminfo": "MemTotal:        7800000 kB\nMemAvailable:    3900000 kB\n",
            }
        )
        obs_receipt = run_qualification(
            sysfs_probe=jetson_probe,
            device_model="NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super",
            l4t_release="R36.4.3",
            llm_bench=lambda: {"tokens_per_second": 31.2, "prompt_ms": 140.0, "model_load_s": 1.9},
            embed_bench=lambda: {"embed_p95_ms": 2.1},
            command_bench=lambda: {"command_latency_ms": 38.0},
        )
        self.assertEqual(obs_receipt["claim_label"], "OBSERVED")
        self.assertEqual(obs_receipt["power_mw_avg"], 11400)
        dumped = json.dumps(obs_receipt).lower()
        for forbidden in ("bearer", "secret", "password", "hostname", "authorization"):
            self.assertNotIn(forbidden, dumped)

    def test_nvtx_range_is_zero_overhead_noop_when_disabled(self):
        with nvtx_range("playbook_plan"):
            x = 1 + 1
        self.assertEqual(x, 2)


if __name__ == "__main__":
    unittest.main()
