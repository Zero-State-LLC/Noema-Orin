"""Pinned noema-client v0.1.23 loopback proof; run separately on Python >=3.11.

The official client's tests/fake_server.py must be on PYTHONPATH. No other
network destination is allowed and no real-world credential is accepted.
"""
from __future__ import annotations

import json
import os
import socket
import sysconfig
import unittest
from pathlib import Path
from unittest.mock import patch

import noema_client
import noema_orin

from fake_server import FakeNoema, serve_fake
from noema_client.policy import ClientPolicy
from noema_orin.runner import ScriptedAdapter, run
from noema_orin.official_client import OfficialLoopbackClient

SELECTORS = (
    "NOEMA_TOKEN", "NOEMA_SERVER", "NOEMA_CONFIG_DIR", "NOEMA_WORLD_ID",
    "NOEMA_ADMIN_TOKEN", "XDG_CONFIG_HOME",
)


class LoopbackProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("NOEMA_ORIN_ASSERT_INSTALLED") == "1":
            roots = []
            for name in ("purelib", "platlib"):
                root = sysconfig.get_path(name)
                if root is not None:
                    roots.append(Path(root).resolve())
            for module in (noema_client, noema_orin):
                origin = Path(module.__file__).resolve()
                if not any(origin.is_relative_to(root) for root in roots):
                    raise AssertionError(f"{module.__name__} did not import from installed site-packages")
            if noema_client.__version__ != "0.1.23":
                raise AssertionError("unexpected official client version")

    def setUp(self):
        # Both server and SDK are real, but the server exists only on loopback.
        self.env = patch.dict(os.environ, {key: "" for key in SELECTORS})
        self.env.start()
        for key in SELECTORS:
            os.environ.pop(key, None)
        self.fake = FakeNoema()
        self.fake.auto_approve = True
        self.origin, self.httpd, self.thread = serve_fake(self.fake)
        self.assertTrue(self.origin.startswith("http://127.0.0.1:"))
        self.raw_connection = socket.create_connection

        def only_loopback(address, *args, **kwargs):
            if address[0] != "127.0.0.1":
                raise AssertionError("non-loopback connection refused")
            return self.raw_connection(address, *args, **kwargs)

        self.network = patch("socket.create_connection", side_effect=only_loopback)
        self.network.start()
        self.client = None

    def tearDown(self):
        if self.client is not None:
            self.client.close()
        self.network.stop()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self.env.stop()

    def make_client(self, **kwargs):
        self.client = OfficialLoopbackClient(server=self.origin, **kwargs)
        return self.client

    def assert_safe(self, record, status, result, *, handoff=False):
        expected = {
            "status": status, "result": result, "profile": "hosted",
            "source_sha": "619d0674518761aa08462d3f5d5966a917259aa1", "claim_label": "SPECULATIVE",
            "client_version": "UNVERIFIED", "device_metrics": "NOT_COMPUTABLE",
        }
        if handoff:
            expected.update(transport="fake", action="LOOK")
        self.assertEqual(record, expected)
        serialized = json.dumps(record)
        for forbidden in ("tok.fixture-secret", "player.fixture", "ctrl.fixture", "accepted", "settled"):
            self.assertNotIn(forbidden, serialized)

    def test_real_client_look_only_reaches_loopback(self):
        client = self.make_client()
        client.prepare()
        record = run(profile="hosted", fixture={"observation": {"synthetic": True}},
                     client=client, adapter=ScriptedAdapter())
        self.assert_safe(record, "ATTEMPTED", "FAKE_HANDOFF", handoff=True)
        self.assertEqual([c["command"] for c in self.fake.commands],
                         ["ENTER_WORLD", "OBSERVE", "LOOK"])
        self.assertEqual(self.fake.device_starts, 1)
        self.assertEqual(client.submissions, 1)
        self.assertNotIn("tok.fixture-secret", json.dumps(client.model_context()))
        self.assertEqual(client.server, self.origin)

    def test_invalid_proposal_refuses_before_client(self):
        client = self.make_client()
        client.prepare()
        class BadAdapter:
            def decide(self, observation):
                return {"action": "WAIT", "target_id": None, "arguments": {}}
        record = run(profile="hosted", fixture={"observation": {"synthetic": True}},
                     client=client, adapter=BadAdapter())
        self.assert_safe(record, "REFUSED", "INVALID_PROPOSAL")
        self.assertEqual(client.submissions, 0)
        self.assertEqual([c["command"] for c in self.fake.commands], ["ENTER_WORLD", "OBSERVE"])

    def test_seal_refusal_stops_before_enrollment_or_look(self):
        self.fake.accepted_seals = ["sha256:invalid"]
        client = self.make_client()
        with self.assertRaises(Exception):
            client.prepare()
        self.assertEqual(self.fake.device_starts, 0)
        self.assertEqual(self.fake.commands, [])

    def test_discovery_protocol_refuses_before_enrollment_or_look(self):
        original_handle = self.fake.handle

        def incompatible(method, path, body, headers):
            status, payload = original_handle(method, path, body, headers)
            if path == "/.well-known/noema-agent.json":
                payload = {**payload, "protocol": "incompatible/v0"}
            return status, payload

        self.fake.handle = incompatible
        client = self.make_client()
        with self.assertRaises(Exception):
            client.prepare()
        self.assertEqual(self.fake.device_starts, 0)
        self.assertEqual(self.fake.commands, [])

    def test_policy_denial_is_failed_submission(self):
        client = self.make_client(policy=ClientPolicy(denied_actions=["LOOK"]))
        client.prepare()
        record = run(profile="hosted", fixture={"observation": {"synthetic": True}},
                     client=client, adapter=ScriptedAdapter())
        self.assert_safe(record, "FAILED_SUBMISSION", "TRANSPORT_FAILURE", handoff=True)
        self.assertEqual(client.submissions, 1)
        self.assertEqual([c["command"] for c in self.fake.commands], ["ENTER_WORLD", "OBSERVE"])

    def test_lost_loopback_transport_is_failed_submission(self):
        client = self.make_client()
        client.prepare()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        record = run(profile="hosted", fixture={"observation": {"synthetic": True}},
                     client=client, adapter=ScriptedAdapter())
        self.assert_safe(record, "FAILED_SUBMISSION", "TRANSPORT_FAILURE", handoff=True)
        self.assertEqual(client.submissions, 1)
        self.assertEqual([c["command"] for c in self.fake.commands], ["ENTER_WORLD", "OBSERVE"])

    def test_unsuccessful_command_result_is_failed_submission(self):
        self.fake.fail_command = "LOOK"
        client = self.make_client()
        client.prepare()
        record = run(profile="hosted", fixture={"observation": {"synthetic": True}},
                     client=client, adapter=ScriptedAdapter())
        self.assert_safe(record, "FAILED_SUBMISSION", "TRANSPORT_FAILURE", handoff=True)
        self.assertEqual(client.submissions, 1)
        self.assertEqual([c["command"] for c in self.fake.commands],
                         ["ENTER_WORLD", "OBSERVE", "LOOK"])

    def test_non_loopback_destination_is_rejected_before_sdk_construction(self):
        for server in ("https://noema.guru", "http://localhost:80", "http://127.0.0.1:80/path",
                       "http://127.0.0.1:80@elsewhere.example", "http://127.0.0.2:80"):
            with self.subTest(server=server), self.assertRaises(ValueError):
                OfficialLoopbackClient(server=server)
        self.assertEqual(self.fake.device_starts, 0)

    def test_inherited_selector_refuses_before_sdk_construction(self):
        with patch.dict(os.environ, {"NOEMA_TOKEN": "fixture-inherited-credential"}):
            with self.assertRaises(ValueError):
                OfficialLoopbackClient(server=self.origin)
        self.assertEqual(self.fake.device_starts, 0)

    def test_discovered_external_command_uri_refuses_before_command(self):
        original_handle = self.fake.handle

        def poisoned(method, path, body, headers):
            status, payload = original_handle(method, path, body, headers)
            if path == "/.well-known/noema-agent.json":
                payload = {**payload, "command_uri": "https://outside.invalid/v1/command"}
            return status, payload

        self.fake.handle = poisoned
        client = self.make_client()
        with self.assertRaises(ValueError):
            client.prepare()
        self.assertEqual(self.fake.device_starts, 0)
        self.assertEqual(self.fake.commands, [])

    def test_http_callable_refuses_discovered_external_target(self):
        client = self.make_client()
        with self.assertRaises(ValueError):
            client._client._http("GET", "https://outside.invalid/.well-known/noema-agent.json")
        self.assertEqual(self.fake.device_starts, 0)

    def test_discovery_redirect_never_leaves_loopback(self):
        self.fake.handle = lambda method, path, body, headers: (302, {"location": "https://noema.guru/"})
        client = self.make_client()
        with self.assertRaises(Exception):
            client.prepare()
        self.assertEqual(client.submissions, 0)
        self.assertEqual(self.fake.device_starts, 0)

    def test_client_owns_and_removes_fixture_credential_directory(self):
        client = self.make_client()
        config = Path(client._client.config_home)
        self.assertTrue(config.is_dir())
        self.assertFalse(config.is_symlink())
        self.assertEqual(config.stat().st_mode & 0o077, 0)
        client.prepare()
        self.assertTrue((config / "credential.json").is_file())
        client.close()
        self.assertFalse(config.exists())
        self.client = None

    def test_caller_cannot_supply_config_path(self):
        # No caller-controlled path, whether a symlink or an empty persistent dir.
        with self.assertRaises(TypeError):
            OfficialLoopbackClient(**{"server": self.origin, "config_home": Path.home()})
        self.assertEqual(self.fake.device_starts, 0)
