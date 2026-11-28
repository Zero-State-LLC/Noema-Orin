"""D-093: at most one notice per room per world cycle.

The engine keeps one `institution_notice` per room and drops it after 1 committed cycle
(`NOTICE_EXPIRE_AFTER_CYCLES = 1`, communication.ts); a second post in the same room and cycle only overwrites
the first. 34 of m05's 130 notices were such overwrites, each costing a MESSAGE budget and a turn.
"""
from __future__ import annotations

import importlib.util
import unittest

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None
ORG = "org.reach-compact.1"


def _obs(cycle: int, room: str = "room.civic-exchange") -> dict:
    return {
        "self": "player.Cantor-Speaker", "sequence": 1000 + cycle, "cycle": cycle,
        "location": {"room_id": room, "entities": [], "exits": []},
        "resources": {"attention": 8, "compute": 10, "energy": 9, "influence": 40, "storage": 16},
        "organizations": [{"org_id": ORG, "my_role": "member",
                           "offices": [{"office_id": "office.notice", "authority_profile": "PUBLISH_NOTICE",
                                        "status": "OCCUPIED", "holder_handle": "Cantor-Speaker"}]}],
        "affordances": [
            {"action": "ORG_OFFICE_ACT", "available": True, "authority_profile": "PUBLISH_NOTICE", "kind": "org",
             "operation": "ORG_OFFICE_ACT", "org_id": ORG, "target_id": ORG, "cmd": f"office act {ORG} notice",
             "verb": "COMMIT"},
            {"action": "WAIT", "available": True},
        ],
        "inventory": [],
    }


@unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
class NoticeOncePerCycle(unittest.TestCase):
    def _speaker(self, tmp):
        from pathlib import Path

        from noema_orin.memory import Memory
        from noema_orin.orin_adapter import OrinAdapter
        from noema_orin.roles import role_for

        spec = role_for("speaker")
        a = OrinAdapter(base_url="http://127.0.0.1:9/v1", model="m", brief="b")
        a.allowed = frozenset(spec["allow"])
        a.verbs = set(spec["verbs"])
        a.default_args = dict(spec.get("args") or {})
        a.health.role = "Cantor-speaker"
        a.memory = Memory(Path(tmp) / "mind")
        for i in range(3):
            a.memory.remember(f"Salvage Cache holds {900 + i} materials available to harvest.",
                              kind="consequence", room="room.civic-exchange", sequence=10 + i)
        return a

    def _step(self, a, obs):
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()):
            p = a.decide({"canonical": obs})
        return p, a.last_playbook_state

    def test_second_notice_in_the_same_room_and_cycle_is_skipped(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            a = self._speaker(d)
            try:
                p1, s1 = self._step(a, _obs(5))
                self.assertEqual((p1.action, s1), ("ORG_OFFICE_ACT", "PUBLISH_NOTICE"))
                p2, s2 = self._step(a, _obs(5))
                self.assertNotEqual(s2, "PUBLISH_NOTICE", "same room, same cycle: the post would only overwrite")
                p3, s3 = self._step(a, _obs(6))
                self.assertEqual(s3, "PUBLISH_NOTICE", "next cycle: the old notice has expired")
                p4, s4 = self._step(a, _obs(6, room="room.relay-quarter"))
                self.assertEqual(s4, "PUBLISH_NOTICE", "another room has its own notice slot")
            finally:
                a.memory.close()

    def test_unknown_cycle_does_not_block_posting(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            a = self._speaker(d)
            try:
                obs = _obs(5)
                obs.pop("cycle")
                self.assertEqual(self._step(a, obs)[1], "PUBLISH_NOTICE")
                self.assertEqual(self._step(a, dict(obs, sequence=2000))[1], "PUBLISH_NOTICE")
            finally:
                a.memory.close()


if __name__ == "__main__":
    unittest.main()
