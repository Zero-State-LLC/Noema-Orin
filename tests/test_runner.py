"""Public runner and CLI behavior for the hosted synthetic Controller."""

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from noema_orin.runner import FakeClient, ScriptedAdapter, run

ROOT = Path(__file__).resolve().parents[1]


class HostedRunnerTests(unittest.TestCase):
    def test_one_hosted_look_submission_is_only_attempted(self):
        client = FakeClient()
        outcome = run(profile="hosted", fixture={"observation": {"synthetic": True}}, client=client, adapter=ScriptedAdapter())
        self.assertEqual(client.attempts, [{"action": "LOOK", "target_id": None, "arguments": {}}])
        self.assertEqual(outcome["status"], "ATTEMPTED")
        self.assertEqual(outcome["profile"], "hosted")
        self.assertEqual(outcome["transport"], "fake")
        self.assertNotIn("accepted", outcome)
        self.assertNotIn("settled", outcome)

    def test_cli_emits_one_json_record_without_network(self):
        result = subprocess.run(
            [sys.executable, "-m", "noema_orin", "--profile", "hosted", "--fixture", str(ROOT / "fixtures/hosted-look.json"), "--dry-run"],
            cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1)
        record = json.loads(result.stdout)
        self.assertEqual((record["status"], record["profile"], record["transport"]), ("ATTEMPTED", "hosted", "fake"))


if __name__ == "__main__":
    unittest.main()
