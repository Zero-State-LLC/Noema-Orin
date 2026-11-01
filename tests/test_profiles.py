"""Public synthetic runner and CLI failure-boundary contracts (#2)."""

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from noema_orin.runner import FakeClient, ScriptedAdapter, run

ROOT = Path(__file__).resolve().parents[1]


class ProbeAdapter:
    def __init__(self, proposal=None):
        self.calls = 0
        self.proposal = proposal or {"action": "LOOK", "target_id": None, "arguments": {}}

    def decide(self, observation):
        self.calls += 1
        return self.proposal


class FailingClient(FakeClient):
    def submit(self, proposal):
        super().submit(proposal)
        raise RuntimeError("TOP_SECRET_EXCEPTION_MARKER")


def invoke(*args):
    return subprocess.run(
        [sys.executable, "-m", "noema_orin", *args], cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True, text=True, check=False,
    )


def single_record(test, result, status):
    test.assertNotEqual(result.returncode, 0)
    test.assertEqual(result.stderr, "")
    test.assertEqual(len(result.stdout.splitlines()), 1)
    record = json.loads(result.stdout)
    test.assertEqual(record["status"], status)
    return record


class ProfileIsolationTests(unittest.TestCase):
    def test_blocked_profile_precedes_fixture_and_all_collaborators(self):
        class UnreadableFixture(dict):
            def __getitem__(self, key):
                raise AssertionError("fixture accessed before profile validation")

        client, adapter = FakeClient(), ProbeAdapter()
        record = run(profile="offline-spark", fixture=UnreadableFixture(), client=client, adapter=adapter)
        self.assertEqual((record["status"], record["result"]), ("REFUSED", "BLOCKED_SPEC_DEFECT"))
        self.assertEqual((client.attempts, adapter.calls), ([], 0))
        cli = invoke("--profile", "offline-spark", "--fixture", "fixtures/not-here.json", "--dry-run")
        record = single_record(self, cli, "REFUSED")
        self.assertEqual(record["result"], "BLOCKED_SPEC_DEFECT")

    def test_missing_and_unknown_profiles_never_echo_raw_input(self):
        for args in (("--fixture", "SECRET_PATH_DO_NOT_ECHO", "--dry-run"),
                     ("--profile", "UNKNOWN_PROFILE_SECRET", "--fixture", "SECRET_PATH_DO_NOT_ECHO", "--dry-run")):
            with self.subTest(args=args):
                result = invoke(*args)
                record = single_record(self, result, "REFUSED")
                self.assertEqual(record["result"], "INVALID_PROFILE")
                self.assertNotIn("UNKNOWN_PROFILE_SECRET", result.stdout + result.stderr)
                self.assertNotIn("SECRET_PATH_DO_NOT_ECHO", result.stdout + result.stderr)

    def test_invalid_hosted_fixture_stops_before_adapter_or_client(self):
        for fixture in ({}, {"observation": []}):
            with self.subTest(fixture=fixture):
                client, adapter = FakeClient(), ProbeAdapter()
                record = run(profile="hosted", fixture=fixture, client=client, adapter=adapter)
                self.assertEqual((record["status"], record["result"]), ("REFUSED", "INVALID_FIXTURE"))
                self.assertEqual((client.attempts, adapter.calls), ([], 0))
        result = invoke("--profile", "hosted", "--fixture", "fixtures/not-here.json", "--dry-run")
        self.assertEqual(single_record(self, result, "REFUSED")["result"], "INVALID_FIXTURE")

    def test_invalid_proposal_never_reaches_client(self):
        for proposal in ({"action": "DELETE", "target_id": None, "arguments": {}},
                         {"action": "LOOK", "target_id": None, "arguments": {}, "prompt": "SECRET"},
                         {"action": "LOOK", "target_id": "x", "arguments": {}},
                         {"action": "LOOK", "target_id": None, "arguments": []}):
            with self.subTest(proposal=proposal):
                client, adapter = FakeClient(), ProbeAdapter(proposal)
                record = run(profile="hosted", fixture={"observation": {}}, client=client, adapter=adapter)
                self.assertEqual((record["status"], record["result"]), ("REFUSED", "INVALID_PROPOSAL"))
                self.assertEqual(client.attempts, [])
                self.assertEqual(adapter.calls, 1)
                self.assertNotIn("SECRET", json.dumps(record))

    def test_invalid_cli_invocations_produce_only_one_record(self):
        for args, expected in (
            (("--help",), "INVALID_INVOCATION"),
            (("--profile", "hosted", "--fixture", "fixtures/hosted-look.json"), "DRY_RUN_REQUIRED"),
            (("--profile", "hosted", "--fixture", "fixtures/not-here.json", "--dry-run"), "INVALID_FIXTURE"),
        ):
            with self.subTest(args=args):
                record = single_record(self, invoke(*args), "REFUSED")
                self.assertEqual(record["result"], expected)

    def test_transport_failure_is_one_submission_without_fallback(self):
        client, adapter = FailingClient(), ProbeAdapter()
        record = run(profile="hosted", fixture={"observation": {}}, client=client, adapter=adapter)
        self.assertEqual((record["status"], record["result"]), ("FAILED_SUBMISSION", "TRANSPORT_FAILURE"))
        self.assertEqual(len(client.attempts), 1)
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(record["profile"], "hosted")
        self.assertNotIn("TOP_SECRET_EXCEPTION_MARKER", json.dumps(record))


if __name__ == "__main__":
    unittest.main()
