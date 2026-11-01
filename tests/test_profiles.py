"""Public synthetic runner and CLI failure-boundary contracts (#2)."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from noema_orin.runner import FakeClient, ScriptedAdapter, run

ROOT = Path(__file__).resolve().parents[1]


class ProbeAdapter:
    def __init__(self, proposal=None):
        self.calls = 0
        self.proposal = proposal if proposal is not None else {"action": "LOOK", "target_id": None, "arguments": {}}

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

    def test_hostile_profile_refuses_before_any_collaborator(self):
        class HostileProfile(str):
            def __eq__(self, other):
                raise RuntimeError("SENTINEL_PROFILE_EXCEPTION")

            def __hash__(self):
                raise RuntimeError("SENTINEL_PROFILE_EXCEPTION")

        client, adapter = FakeClient(), ProbeAdapter()
        record = run(profile=HostileProfile("hosted"), fixture={"observation": {"synthetic": True}}, client=client, adapter=adapter)
        self.assertEqual((record["status"], record["result"]), ("REFUSED", "INVALID_PROFILE"))
        self.assertEqual((client.attempts, adapter.calls), ([], 0))
        self.assertNotIn("SENTINEL_", json.dumps(record))

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
        for fixture in ({}, {"observation": []}, {"observation": {}}, {"observation": {"synthetic": False}}):
            with self.subTest(fixture=fixture):
                client, adapter = FakeClient(), ProbeAdapter()
                record = run(profile="hosted", fixture=fixture, client=client, adapter=adapter)
                self.assertEqual((record["status"], record["result"]), ("REFUSED", "INVALID_FIXTURE"))
                self.assertEqual((client.attempts, adapter.calls), ([], 0))
        result = invoke("--profile", "hosted", "--fixture", "fixtures/not-here.json", "--dry-run")
        self.assertEqual(single_record(self, result, "REFUSED")["result"], "INVALID_FIXTURE")

    def test_invalid_proposal_never_reaches_client(self):
        for proposal in ({}, {"action": "DELETE", "target_id": None, "arguments": {}},
                         {"action": "LOOK", "target_id": None, "arguments": {}, "prompt": "SECRET"},
                         {"action": "LOOK", "target_id": "x", "arguments": {}},
                         {"action": "LOOK", "target_id": None, "arguments": []}):
            with self.subTest(proposal=proposal):
                client, adapter = FakeClient(), ProbeAdapter(proposal)
                record = run(profile="hosted", fixture={"observation": {"synthetic": True}}, client=client, adapter=adapter)
                self.assertEqual((record["status"], record["result"]), ("REFUSED", "INVALID_PROPOSAL"))
                self.assertEqual(client.attempts, [])
                self.assertEqual(adapter.calls, 1)
                self.assertNotIn("SECRET", json.dumps(record))

    def test_fixture_access_exception_refuses_before_adapter_and_client(self):
        class HostileFixture(dict):
            def __getitem__(self, key):
                raise RuntimeError("SENTINEL_FIXTURE_EXCEPTION")

        client, adapter = FakeClient(), ProbeAdapter()
        record = run(profile="hosted", fixture=HostileFixture(), client=client, adapter=adapter)
        self.assertEqual((record["status"], record["result"]), ("REFUSED", "INVALID_FIXTURE"))
        self.assertEqual((client.attempts, adapter.calls), ([], 0))
        self.assertNotIn("SENTINEL_", json.dumps(record))

    def test_hostile_observation_refuses_before_adapter_and_client(self):
        class HostileObservation(dict):
            def get(self, key, default=None):
                raise RuntimeError("SENTINEL_OBSERVATION_EXCEPTION")

        client, adapter = FakeClient(), ProbeAdapter()
        record = run(profile="hosted", fixture={"observation": HostileObservation()}, client=client, adapter=adapter)
        self.assertEqual((record["status"], record["result"]), ("REFUSED", "INVALID_FIXTURE"))
        self.assertEqual((client.attempts, adapter.calls), ([], 0))
        self.assertNotIn("SENTINEL_", json.dumps(record))

    def test_lying_fixture_lookup_refuses_before_adapter_and_client(self):
        class LyingFixture(dict):
            def __getitem__(self, key):
                return {"synthetic": True}

        client, adapter = FakeClient(), ProbeAdapter()
        record = run(profile="hosted", fixture=LyingFixture(observation={"synthetic": False}), client=client, adapter=adapter)
        self.assertEqual((record["status"], record["result"]), ("REFUSED", "INVALID_FIXTURE"))
        self.assertEqual((client.attempts, adapter.calls), ([], 0))

    def test_lying_observation_get_refuses_before_adapter_and_client(self):
        class LyingObservation(dict):
            def get(self, key, default=None):
                return True

        client, adapter = FakeClient(), ProbeAdapter()
        record = run(profile="hosted", fixture={"observation": LyingObservation(synthetic=False)}, client=client, adapter=adapter)
        self.assertEqual((record["status"], record["result"]), ("REFUSED", "INVALID_FIXTURE"))
        self.assertEqual((client.attempts, adapter.calls), ([], 0))

    def test_deeply_nested_fixture_refuses_with_one_safe_cli_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested.json"
            path.write_text('{"observation":' + '[' * 1500 + '0' + ']' * 1500 + '}', encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-c", "import json,runpy,sys; json.loads=lambda _: (_ for _ in ()).throw(RecursionError('SENTINEL_FIXTURE_EXCEPTION')); sys.argv=['noema_orin', '--profile', 'hosted', '--fixture', sys.argv[1], '--dry-run']; runpy.run_module('noema_orin', run_name='__main__')", str(path)],
                cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                capture_output=True, text=True, check=False,
            )
        record = single_record(self, result, "REFUSED")
        self.assertEqual(record["result"], "INVALID_FIXTURE")
        self.assertNotIn("SENTINEL_FIXTURE_EXCEPTION", result.stdout + result.stderr)

    def test_adversarial_proposal_validation_refuses_before_submit(self):
        class HostileValue:
            def __eq__(self, other):
                raise RuntimeError("SENTINEL_PROPOSAL_EXCEPTION")

        class HostileProposal(dict):
            def __iter__(self):
                raise RuntimeError("SENTINEL_ITER_EXCEPTION")

        for proposal in (
            {"action": HostileValue(), "target_id": None, "arguments": {}},
            HostileProposal(action="LOOK", target_id=None, arguments={}),
        ):
            with self.subTest(proposal=type(proposal).__name__):
                client, adapter = FakeClient(), ProbeAdapter(proposal)
                record = run(profile="hosted", fixture={"observation": {"synthetic": True}}, client=client, adapter=adapter)
                self.assertEqual((record["status"], record["result"]), ("REFUSED", "INVALID_PROPOSAL"))
                self.assertEqual((client.attempts, adapter.calls), ([], 1))
                self.assertNotIn("SENTINEL_", json.dumps(record))

    def test_fixture_with_string_subclass_marker_key_refuses_before_adapter(self):
        class AliasKey(str):
            pass

        client, adapter = FakeClient(), ProbeAdapter()
        record = run(profile="hosted", fixture={"observation": {AliasKey("synthetic"): True}}, client=client, adapter=adapter)
        self.assertEqual((record["status"], record["result"]), ("REFUSED", "INVALID_FIXTURE"))
        self.assertEqual((client.attempts, adapter.calls), ([], 0))

    def test_proposal_with_string_subclass_key_refuses_before_submit(self):
        class AliasKey(str):
            pass

        proposal = {AliasKey("action"): "LOOK", "target_id": None, "arguments": {}}
        client, adapter = FakeClient(), ProbeAdapter(proposal)
        record = run(profile="hosted", fixture={"observation": {"synthetic": True}}, client=client, adapter=adapter)
        self.assertEqual((record["status"], record["result"]), ("REFUSED", "INVALID_PROPOSAL"))
        self.assertEqual((client.attempts, adapter.calls), ([], 1))

    def test_invalid_cli_invocations_produce_only_one_record(self):
        for args, expected in (
            (("--help",), "INVALID_INVOCATION"),
            (("--profile", "hosted", "--fixture", "fixtures/hosted-look.json"), "DRY_RUN_REQUIRED"),
            (("--profile", "hosted", "--fixture", "fixtures/not-here.json", "--dry-run"), "INVALID_FIXTURE"),
        ):
            with self.subTest(args=args):
                record = single_record(self, invoke(*args), "REFUSED")
                self.assertEqual(record["result"], expected)

    def test_cli_transport_failure_is_one_failed_handoff_and_one_safe_record(self):
        from noema_orin.__main__ import main

        client = FailingClient()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("noema_orin.__main__.FakeClient", return_value=client):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(["--profile", "hosted", "--fixture", "fixtures/hosted-look.json", "--dry-run"])
        self.assertNotEqual(code, 0)
        self.assertEqual(len(client.attempts), 1)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)
        record = json.loads(stdout.getvalue())
        self.assertEqual(record["status"], "FAILED_SUBMISSION")
        self.assertNotIn("TOP_SECRET_EXCEPTION_MARKER", stdout.getvalue() + stderr.getvalue())

    def test_transport_failure_is_one_submission_without_fallback(self):
        client, adapter = FailingClient(), ProbeAdapter()
        record = run(profile="hosted", fixture={"observation": {"synthetic": True}}, client=client, adapter=adapter)
        self.assertEqual((record["status"], record["result"]), ("FAILED_SUBMISSION", "TRANSPORT_FAILURE"))
        self.assertEqual(len(client.attempts), 1)
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(record["profile"], "hosted")
        self.assertNotIn("TOP_SECRET_EXCEPTION_MARKER", json.dumps(record))


if __name__ == "__main__":
    unittest.main()
