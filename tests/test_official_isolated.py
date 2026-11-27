"""T4 (#4): isolated official-client wrapper, proven against a fake client (no network)."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

from noema_orin.official_isolated import OfficialIsolatedClient, admit_world

JWT = "aaa.bbb.ccc"
TOKEN = "ttt.uuu.vvv"
WORLD = "test.hosted-canonical.orin-t4"
LOOK = {"action": "LOOK", "target_id": None, "arguments": {}}


class FakeClient:
    instances: list["FakeClient"] = []

    def __init__(self, server, **kw):
        self.server, self.kw = server, kw
        self.cred = (kw["config_home"] / "cred").read_text()
        self.acts, self.connected, self.closed = [], False, False
        self.ok = True
        self.leak = False
        FakeClient.instances.append(self)

    def connect(self, *, auto_enter=True):
        self.connected = auto_enter

    def model_context(self):
        return {"room": "x", "note": self.cred if self.leak else "safe"}

    def act(self, proposal):
        self.acts.append(proposal)
        return SimpleNamespace(ok=self.ok)

    def close(self):
        self.closed = True


def make(**over):
    kw = dict(world_id=WORLD, controller_token=TOKEN, admin_jwt=JWT, client_factory=FakeClient,
              client_version="0.2.0",
              credential_writer=lambda home: open(os.path.join(home, "cred"), "w").write(TOKEN))
    kw.update(over)
    return OfficialIsolatedClient(**kw)


class AdmissionTests(unittest.TestCase):
    def test_only_isolated_worlds_are_admitted(self):
        self.assertEqual(admit_world(WORLD), WORLD)
        for bad in ("", "world-01", "world.perihelion-reach", "test.hosted-canonical.",
                    "test.hosted-canonical.perihelion", "test.hosted-canonical..x",
                    "test.other.x"):
            with self.assertRaises(ValueError, msg=bad):
                admit_world(bad)

    def test_seal_refusals(self):
        with self.assertRaises(ValueError):
            make(server="https://evil.example")
        with self.assertRaises(ValueError):
            make(admin_jwt="raw-operator-secret")
        with self.assertRaises(ValueError):
            make(controller_token="")
        with self.assertRaises(ValueError):
            make(client_version="0.1.23")


class SeamTests(unittest.TestCase):
    def test_isolated_http_construction_and_one_look(self):
        c = make()
        fake = FakeClient.instances[-1]
        self.assertTrue(fake.kw["isolated"])
        self.assertEqual(fake.kw["transport"], "http")
        self.assertEqual(fake.kw["world_id"], WORLD)
        self.assertEqual(fake.cred, TOKEN)
        with self.assertRaises(RuntimeError):
            c.submit(LOOK)
        c.prepare()
        self.assertTrue(fake.connected)
        c.submit(LOOK)
        self.assertEqual(c.submissions, 1)
        home = fake.kw["config_home"]
        c.close()
        self.assertTrue(fake.closed)
        self.assertFalse(home.exists())

    def test_proposal_validation(self):
        c = make()
        c.prepare()
        for bad in ({"action": "MOVE", "target_id": None, "arguments": {}},
                    {"action": "LOOK", "target_id": "x", "arguments": {}},
                    {"action": "LOOK", "target_id": None, "arguments": {"a": 1}},
                    {"action": "LOOK"}):
            with self.assertRaises(ValueError):
                c.submit(bad)
        self.assertEqual(c.submissions, 0)

    def test_rejection_is_a_failed_handoff(self):
        c = make()
        c.prepare()
        FakeClient.instances[-1].ok = False
        with self.assertRaises(RuntimeError):
            c.submit(LOOK)

    def test_no_credential_in_model_context(self):
        c = make()
        self.assertEqual(c.model_context()["note"], "safe")
        FakeClient.instances[-1].leak = True
        with self.assertRaises(RuntimeError):
            c.model_context()


if __name__ == "__main__":
    unittest.main()
