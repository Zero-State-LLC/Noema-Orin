"""Controller group dry run (T7, D-006/D-007)."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import unittest

from noema_orin.group import run_group
from noema_orin.runner import FakeClient, ScriptedAdapter

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = {"observation": {"synthetic": True}}


class FailingClient(FakeClient):
    def submit(self, proposal):
        super().submit(proposal)
        raise RuntimeError("boom")


class GroupTests(unittest.TestCase):
    def test_six_members_each_get_own_identity_client_and_receipt(self):
        clients = []
        def make_client(member_id):
            clients.append((member_id, FakeClient()))
            return clients[-1][1]
        members, summary = run_group(profile="hosted", fixture=FIXTURE, size=6,
                                     client_factory=make_client, adapter_factory=lambda m: ScriptedAdapter())
        ids = [m["member_id"] for m in members]
        self.assertEqual(ids, [f"member-{i:02d}" for i in range(1, 7)])
        self.assertEqual(len({id(c) for _, c in clients}), 6)
        self.assertTrue(all(len(c.attempts) == 1 for _, c in clients))
        self.assertTrue(all(m["status"] == "ATTEMPTED" for m in members))
        self.assertEqual(summary["group_status"], "ATTEMPTED")
        self.assertEqual(summary["counts"], {"ATTEMPTED": 6, "FAILED_SUBMISSION": 0, "REFUSED": 0, "STOPPED": 0})

    def test_one_member_failure_is_isolated_and_partial(self):
        def make_client(member_id):
            return FailingClient() if member_id == "member-03" else FakeClient()
        members, summary = run_group(profile="hosted", fixture=FIXTURE, size=6,
                                     client_factory=make_client, adapter_factory=lambda m: ScriptedAdapter())
        statuses = [m["status"] for m in members]
        self.assertEqual(statuses.count("FAILED_SUBMISSION"), 1)
        self.assertEqual(statuses.count("ATTEMPTED"), 5)
        self.assertEqual(summary["group_status"], "PARTIAL")

    def test_group_stop_halts_remaining_members(self):
        stop = threading.Event()
        def make_client(member_id):
            if member_id == "member-02":
                stop.set()
            return FakeClient()
        members, summary = run_group(profile="hosted", fixture=FIXTURE, size=6, stop=stop,
                                     client_factory=make_client, adapter_factory=lambda m: ScriptedAdapter())
        self.assertEqual(summary["counts"]["STOPPED"], 4)
        self.assertEqual(summary["group_status"], "STOPPED")

    def test_blocked_profile_refuses_whole_group_before_members(self):
        made = []
        members, summary = run_group(profile="offline-spark", fixture=FIXTURE, size=6,
                                     client_factory=lambda m: made.append(m) or FakeClient(), adapter_factory=lambda m: ScriptedAdapter())
        self.assertEqual(made, [])
        self.assertEqual(members, [])
        self.assertEqual(summary["group_status"], "REFUSED")

    def test_invalid_size_refuses(self):
        for size in (0, -1, 7, True, "6"):
            _, summary = run_group(profile="hosted", fixture=FIXTURE, size=size,
                                   client_factory=lambda m: FakeClient(), adapter_factory=lambda m: ScriptedAdapter())
            self.assertEqual(summary["group_status"], "REFUSED", size)


class GroupCliTests(unittest.TestCase):
    def _cli(self, *extra):
        return subprocess.run(
            [sys.executable, "-m", "noema_orin", "--profile", "hosted", "--fixture",
             str(ROOT / "fixtures/hosted-look.json"), "--dry-run", *extra],
            cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True, check=False)

    def test_cli_group_emits_member_lines_then_summary(self):
        result = self._cli("--group", "6")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        lines = [json.loads(l) for l in result.stdout.splitlines()]
        self.assertEqual(len(lines), 7)
        self.assertEqual(lines[-1]["group_status"], "ATTEMPTED")
        self.assertEqual(lines[-1]["group_size"], 6)

    def test_cli_bad_group_size_refuses_one_line(self):
        result = self._cli("--group", "99")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["group_status"], "REFUSED")

    def test_sigterm_is_group_stop(self):
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "NOEMA_ORIN_TEST_MEMBER_DELAY": "0.3"}
        proc = subprocess.Popen(
            [sys.executable, "-m", "noema_orin", "--profile", "hosted", "--fixture",
             str(ROOT / "fixtures/hosted-look.json"), "--dry-run", "--group", "6"],
            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        import time; time.sleep(0.5)
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=10)
        self.assertEqual(err, "")
        summary = json.loads(out.splitlines()[-1])
        self.assertEqual(summary["group_status"], "STOPPED")
        self.assertGreater(summary["counts"]["STOPPED"], 0)
        self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
