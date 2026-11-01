"""Top-level provenance and secret-safe synthetic outcome contracts (#3)."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from noema_orin.runner import FakeClient, ScriptedAdapter, run

ROOT = Path(__file__).resolve().parents[1]
PIN = "619d0674518761aa08462d3f5d5966a917259aa1"
SECRETS = ["SENTINEL_TOKEN_9172", "SENTINEL_PROMPT_3460", "SENTINEL_BROWSER_7771", "SENTINEL_AUTH_HEADER_9841"]


class SecretClient(FakeClient):
    def submit(self, proposal):
        super().submit(proposal)
        return {"authorization": SECRETS[3], "accepted": True}


class SecretAdapter(ScriptedAdapter):
    def decide(self, observation):
        return {"action": "LOOK", "target_id": None, "arguments": {}}


class RaisingClient(FakeClient):
    def submit(self, proposal):
        super().submit(proposal)
        raise RuntimeError("SENTINEL_EXCEPTION_8004")


class ReceiptTests(unittest.TestCase):
    def test_runner_receipt_allowlists_fields_not_client_payload_or_observation(self):
        client = SecretClient()
        record = run(profile="hosted", fixture={"observation": {"synthetic": True, "token": SECRETS[0], "prompt": SECRETS[1], "browser_credential": SECRETS[2]}}, client=client, adapter=SecretAdapter())
        self.assertEqual(len(client.attempts), 1)
        self.assertEqual(record, {
            "status": "ATTEMPTED", "profile": "hosted", "transport": "fake",
            "source_sha": PIN, "action": "LOOK", "result": "FAKE_HANDOFF",
            "claim_label": "SPECULATIVE", "client_version": "UNVERIFIED", "device_metrics": "NOT_COMPUTABLE",
        })
        self.assertTrue(all(secret not in json.dumps(record) for secret in SECRETS))
        self.assertNotIn("accepted", json.dumps(record).lower())

    def test_refusal_and_failed_handoff_have_safe_provenance(self):
        refusal = run(profile="SENTINEL_PROFILE_1610", fixture=None, client=FakeClient(), adapter=ScriptedAdapter())
        self.assertEqual(refusal, {
            "status": "REFUSED", "result": "INVALID_PROFILE", "source_sha": PIN,
            "claim_label": "SPECULATIVE", "client_version": "UNVERIFIED", "device_metrics": "NOT_COMPUTABLE",
        })
        client = RaisingClient()
        failed = run(profile="hosted", fixture={"observation": {"synthetic": True}}, client=client, adapter=ScriptedAdapter())
        self.assertEqual(len(client.attempts), 1)
        self.assertEqual(failed, {
            "status": "FAILED_SUBMISSION", "result": "TRANSPORT_FAILURE", "source_sha": PIN,
            "claim_label": "SPECULATIVE", "client_version": "UNVERIFIED", "device_metrics": "NOT_COMPUTABLE",
            "profile": "hosted", "transport": "fake", "action": "LOOK",
        })
        self.assertNotIn("SENTINEL_EXCEPTION_8004", json.dumps(failed))
        self.assertNotIn("SENTINEL_PROFILE_1610", json.dumps(refusal))

    def test_cli_never_echoes_sentinel_inputs_and_emits_one_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps({"observation": {"synthetic": True, "token": SECRETS[0], "prompt": SECRETS[1], "browser_credential": SECRETS[2]}}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "noema_orin", "--profile", "hosted", "--fixture", str(path), "--dry-run"],
                cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1)
        record = json.loads(result.stdout)
        self.assertEqual(record["source_sha"], PIN)
        self.assertEqual(record["claim_label"], "SPECULATIVE")
        for secret in SECRETS:
            self.assertNotIn(secret, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
