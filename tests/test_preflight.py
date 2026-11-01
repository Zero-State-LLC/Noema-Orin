"""Public behavior of the credential-free local inspection command."""

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import cast
import unittest
from unittest.mock import patch

from noema_orin.preflight import HostProbe, run_preflight
from noema_orin.receipts import SOURCE_SHA

ROOT = Path(__file__).resolve().parents[1]
SECRET = "sensitive-host-token-192.0.2.43"


class FakeProbe:
    def __init__(self, values=None, failures=()):
        self.values = {
            "/etc/os-release": 'NAME="Ubuntu"\nID=ubuntu\nVERSION_ID="24.04"\n',
            "/etc/nv_tegra_release": "# R39 (release), REVISION: 2.1, GCID: 0",
            "/proc/device-tree/model": "NVIDIA Jetson Orin Nano Developer Kit\x00",
            "/proc/meminfo": "MemTotal:        7733248 kB\nMemFree: 3000000 kB\n",
            "machine": "aarch64",
            "python_version": "3.12.3",
            "free_bytes": 65 * 1024**3,
            "client_version": "0.1.23",
        }
        self.values.update(values or {})
        self.failures = frozenset(failures)

    def read_text(self, path):
        if path in self.failures:
            raise RuntimeError(SECRET)
        return self.values[path]

    def machine(self):
        return self._get("machine")

    def python_version(self):
        return self._get("python_version")

    def free_bytes(self):
        return self._get("free_bytes")

    def client_version(self):
        return self._get("client_version")

    def _get(self, key):
        if key in self.failures:
            raise RuntimeError(SECRET)
        return self.values[key]


class PreflightTests(unittest.TestCase):
    def test_candidate_receipt_has_only_literal_safe_fields(self):
        self.assertEqual(run_preflight(FakeProbe()), {
            "source_sha": SOURCE_SHA,
            "claim_label": "SPECULATIVE",
            "evidence_scope": "LOCAL_PREFLIGHT_ONLY",
            "machine": "aarch64",
            "os_id": "ubuntu",
            "os_version": "24.04",
            "l4t_release": "R39.2.1",
            "device_family": "JETSON_ORIN_NANO_CANDIDATE",
            "python_version": "3.12.3",
            "client_version": "0.1.23",
            "ram_gib_bucket": "4-8",
            "storage_free_gib_bucket": "64-128",
            "jetpack_version": "NOT_COMPUTABLE",
            "device_metrics": "NOT_COMPUTABLE",
            "model_load": "NOT_COMPUTABLE",
            "tokens_per_second": "NOT_COMPUTABLE",
            "power": "NOT_COMPUTABLE",
            "command_latency": "NOT_COMPUTABLE",
        })

    def test_non_jetson_host_has_no_candidate_claim(self):
        record = run_preflight(FakeProbe({
            "machine": "x86_64", "/proc/device-tree/model": "NVIDIA Jetson AGX Orin\x00",
            "/etc/nv_tegra_release": "", "/etc/os-release": "ID=debian\nVERSION_ID=12\n",
            "client_version": "0.1.23.dev0",
        }))
        self.assertEqual(record["machine"], "x86_64")
        for field in ("device_family", "l4t_release", "os_id", "os_version", "client_version"):
            self.assertEqual(record[field], "NOT_COMPUTABLE")

    def test_poisoned_and_raised_probes_never_echo_secrets(self):
        values = {"machine": SECRET, "python_version": "3.12.3 " + SECRET,
                  "/etc/os-release": "ID=ubuntu\nVERSION_ID=24.04\nVERSION_ID=22.04\n" + SECRET,
                  "/etc/nv_tegra_release": "# R39 (release), REVISION: 2.1 " + SECRET,
                  "/proc/device-tree/model": "NVIDIA Jetson Orin Nano Developer Kit " + SECRET,
                  "/proc/meminfo": "MemTotal: NaN kB\n" + SECRET,
                  "free_bytes": float("inf"), "client_version": SECRET}
        record = run_preflight(FakeProbe(values, failures=("client_version",)))
        text = json.dumps(record)
        self.assertNotIn(SECRET, text)
        for field in ("machine", "python_version", "os_id", "os_version", "l4t_release",
                      "device_family", "ram_gib_bucket", "storage_free_gib_bucket", "client_version"):
            self.assertEqual(record[field], "NOT_COMPUTABLE", field)

    def test_forged_model_or_l4t_tail_cannot_claim_family_or_release(self):
        for model in ("NVIDIA Jetson Orin Nano Developer Kit " + SECRET,
                      "NVIDIA Jetson Orin Nano Developer Kit\x00" + SECRET,
                      "NVIDIA Jetson Orin Nano Developer Kit\n" + SECRET):
            with self.subTest(model=model):
                self.assertEqual(run_preflight(FakeProbe({"/proc/device-tree/model": model}))["device_family"],
                                 "NOT_COMPUTABLE")
        for release in ("# R39 (release), REVISION: 2.1, GCID: 1, SERIAL: " + SECRET,
                        "# R39 (release), REVISION: 2.1 " + SECRET):
            with self.subTest(release=release):
                self.assertEqual(run_preflight(FakeProbe({"/etc/nv_tegra_release": release}))["l4t_release"],
                                 "NOT_COMPUTABLE")

    def test_real_probe_bounds_local_file_read(self):
        from noema_orin.preflight import LocalHostProbe
        from unittest.mock import mock_open
        with patch("pathlib.Path.open", mock_open(read_data="X" * 5000)):
            self.assertEqual(LocalHostProbe().read_text("/etc/os-release"), "")

    def test_raising_probe_attribute_access_is_sanitized(self):
        class RaisingAttributes:
            @property
            def machine(self):
                raise RuntimeError(SECRET)

            @property
            def python_version(self):
                raise RuntimeError(SECRET)

            @property
            def client_version(self):
                raise RuntimeError(SECRET)

            @property
            def free_bytes(self):
                raise RuntimeError(SECRET)

            @property
            def read_text(self):
                raise RuntimeError(SECRET)

        record = run_preflight(cast(HostProbe, RaisingAttributes()))
        self.assertEqual(set(record.values()) - {SOURCE_SHA, "SPECULATIVE", "LOCAL_PREFLIGHT_ONLY"},
                         {"NOT_COMPUTABLE"})
        self.assertNotIn(SECRET, json.dumps(record))

    def test_multiple_nul_suffixes_do_not_claim_device_family(self):
        for model in ("NVIDIA Jetson Orin Nano Developer Kit\x00\x00",
                      "NVIDIA Jetson Orin Nano Developer Kit\x00\x00\x00"):
            with self.subTest(model=model):
                record = run_preflight(FakeProbe({"/proc/device-tree/model": model}))
                self.assertEqual(record["device_family"], "NOT_COMPUTABLE")

    def test_unavailable_probes_are_not_computable(self):
        record = run_preflight(FakeProbe(failures=(
            "/etc/os-release", "/etc/nv_tegra_release", "/proc/device-tree/model",
            "/proc/meminfo", "machine", "python_version", "free_bytes", "client_version")))
        self.assertEqual(set(record.values()) - {SOURCE_SHA, "SPECULATIVE", "LOCAL_PREFLIGHT_ONLY"}, {"NOT_COMPUTABLE"})

    def test_capacity_bucket_boundaries(self):
        for value, expected in ((-1, "NOT_COMPUTABLE"), (0, "0-4"),
                                (4 * 1024**3 - 1, "0-4"), (4 * 1024**3, "4-8"),
                                (8 * 1024**3, "8-16"), (128 * 1024**3, "128+")):
            with self.subTest(value=value):
                record = run_preflight(FakeProbe({"free_bytes": value}))
                self.assertEqual(record["storage_free_gib_bucket"], expected)

    def test_entry_never_launches_process_or_network(self):
        before = set(sys.modules)
        with patch("subprocess.run", side_effect=AssertionError("subprocess")), \
             patch("socket.socket", side_effect=AssertionError("network")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("urlopen")):
            record = run_preflight(FakeProbe())
        self.assertEqual(record["evidence_scope"], "LOCAL_PREFLIGHT_ONLY")
        self.assertNotIn("noema_client", set(sys.modules) - before)

    def test_real_probe_uses_local_metadata_without_importing_client(self):
        from noema_orin.preflight import LocalHostProbe
        before = set(sys.modules)
        with patch("importlib.metadata.version", return_value="0.1.23") as version, \
             patch("subprocess.run", side_effect=AssertionError("subprocess")), \
             patch("socket.socket", side_effect=AssertionError("network")), \
             patch("urllib.request.urlopen", side_effect=AssertionError("urlopen")):
            self.assertEqual(LocalHostProbe().client_version(), "0.1.23")
        version.assert_called_once_with("noema-client")
        self.assertNotIn("noema_client", set(sys.modules) - before)

    def test_cli_one_record_no_errors(self):
        result = subprocess.run([sys.executable, "-m", "noema_orin.preflight"],
                                cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                                capture_output=True, text=True, check=False)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(len(result.stdout.splitlines()), 1)
        record = json.loads(result.stdout)
        self.assertEqual(record["evidence_scope"], "LOCAL_PREFLIGHT_ONLY")
        self.assertEqual(record["device_metrics"], "NOT_COMPUTABLE")
        self.assertEqual(record["source_sha"], SOURCE_SHA)


if __name__ == "__main__":
    unittest.main()
