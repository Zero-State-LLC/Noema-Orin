import tempfile
import unittest
from pathlib import Path

from noema_orin.memory import Memory
from noema_orin.orin_adapter import grounded_notice


class NoticeTests(unittest.TestCase):
    def test_notice_cites_latest_observed_fact_and_skips_movement(self):
        with tempfile.TemporaryDirectory() as d:
            m = Memory(Path(d))
            self.assertIsNone(grounded_notice(m))
            m.remember("An archive annex is under construction (entity.archive-annex.b52f48d1).", kind="consequence",
                       room="room.archive", sequence=62000)
            m.remember("You arrive at Civic Exchange.", kind="consequence", room="room.civic", sequence=62010)
            out = grounded_notice(m, "Reach Compact")
            self.assertIn("archive annex is under construction", out)
            self.assertIn("seq 62000", out)
            self.assertLessEqual(len(out), 280)
            m.close()

    def test_d059_skips_own_echoes_and_posts_each_fact_once(self):
        with tempfile.TemporaryDirectory() as d:
            m = Memory(Path(d))
            m.remember("Relay Quarter relay is failing.", kind="consequence", room="room.r", sequence=10)
            m.remember("Notice posted for Reach Compact.", kind="consequence", room="room.c", sequence=11)
            m.remember("You wait.", kind="consequence", room="room.c", sequence=12)
            self.assertIn("relay is failing", grounded_notice(m))
            self.assertIsNone(grounded_notice(m))
            m.close()


@unittest.skipUnless(__import__("importlib").util.find_spec("noema_client"), "needs noema-client")
class ProposalTests(unittest.TestCase):
    RAW = {"action": "ORG_OFFICE_ACT", "operation": "ORG_OFFICE_ACT", "target_id": "org.x.1",
           "cmd": 'notice org.x.1 "posted"', "available": True}

    def test_office_act_carries_grounded_notice_or_is_skipped(self):
        from noema_orin.orin_adapter import _proposal
        self.assertIsNone(_proposal({"action": "ORG_OFFICE_ACT", "raw": self.RAW}, {}, None))
        with tempfile.TemporaryDirectory() as d:
            m = Memory(Path(d))
            m.remember("Relay Quarter: Infrastructure shows damage.", kind="room", room="room.relay", sequence=5)
            p = _proposal({"action": "ORG_OFFICE_ACT", "raw": self.RAW}, {}, m)
            self.assertEqual(p.arguments["org_id"], "org.x.1")
            self.assertIn("seq 5", p.arguments["notice"])
            m.close()

    def test_loop_break_move_has_direction(self):
        from noema_orin.orin_adapter import OrinAdapter
        a = OrinAdapter.__new__(OrinAdapter)
        a.world_map = None
        ctx = {"canonical": {"location": {"exits": [{"direction": "north", "to_room_id": "room.r"}]}}}
        self.assertEqual(a._loop_break_move(ctx).target_id, "north")
        self.assertEqual(a._loop_break_move({"canonical": {}}).action, "WAIT")

    def test_loop_break_respects_role_without_move(self):
        from noema_orin.orin_adapter import OrinAdapter
        a = OrinAdapter.__new__(OrinAdapter)
        a.world_map = None
        a.allowed = frozenset({"LOOK", "INSPECT", "WAIT", "HARVEST"})
        ctx = {"canonical": {"location": {"exits": [{"direction": "north", "to_room_id": "room.r"}]}}}
        self.assertEqual(a._loop_break_move(ctx).action, "WAIT")

    def test_loop_break_never_moves_without_energy(self):
        from noema_orin.orin_adapter import OrinAdapter
        a = OrinAdapter.__new__(OrinAdapter)
        a.world_map = None
        ctx = {"canonical": {"resources": {"energy": 0, "storage": 16},
                             "location": {"exits": [{"direction": "north", "to_room_id": "room.r"}]}}}
        self.assertEqual(a._loop_break_move(ctx).action, "LOOK")


if __name__ == "__main__":
    unittest.main()
