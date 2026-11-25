"""S8/S10: per-agent work queue in map.db; supply need from blocked work; routing to own work rooms."""
import tempfile
import unittest
from pathlib import Path

from noema_orin.memory import WorldMap
from noema_orin.orin_adapter import _needs_supply, _role_work
from noema_orin.planner import route

C = "player.Rivet-Custodian"


class WorkQueueTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.m = WorldMap(Path(tmp.name))
        for r, ex in (("room.a", ["room.b", "room.x"]), ("room.b", ["room.a", "room.c"]), ("room.c", ["room.b"]),
                      ("room.x", ["room.a"])):
            self.m.observe(r, r, 1, ex, [])

    def test_role_work_classifies_need_and_skips_construct_and_depleted(self):
        c = {"affordances": [
            {"operation": "RESTORE", "target_id": "e.annex", "available": False, "reason": "You do not have materials in hold."},
            {"operation": "REPAIR", "target_id": "e.relay", "available": True},
            {"operation": "CONSTRUCT", "available": True},
            {"operation": "HARVEST", "target_id": "e.node", "available": False, "reason": "Not enough stock available."}]}
        self.assertEqual(_role_work(c, {"RESTORE", "REPAIR", "CONSTRUCT", "HARVEST"}),
                         [("RESTORE", "e.annex", "materials"), ("REPAIR", "e.relay", "")])

    def test_blocked_on_materials_triggers_supply_even_with_cargo(self):
        self.m.locate(C, "room.c", 5, 8, 2)  # 8 aboard, not short by LOW_CARGO
        opt = {"target_id": C, "raw": {"resource": "storage"}}
        self.assertFalse(_needs_supply(opt, "Rivet-Custodian", self.m, set()))
        self.m.record_work(C, "room.c", [("RESTORE", "e.annex", "materials")], 3)
        self.assertTrue(_needs_supply(opt, "Rivet-Custodian", self.m, set()))

    def test_routes_to_own_work_room_nearest(self):
        self.m.record_work(C, "room.c", [("REPAIR", "e.relay", "")], 3)
        self.m.observe("room.x", "x", 9, ["room.a"], ["REPAIR"])  # newer offer elsewhere, but not its own work
        canon = {"location": {"room_id": "room.a", "exits": [{"to_room_id": "room.b", "direction": "east"},
                                                             {"to_room_id": "room.x", "direction": "west"}]}}
        self.assertEqual(route(canon, self.m, {"REPAIR"}, explorer=False, me=C), "east")
        self.m.record_work(C, "room.c", [], 4)  # work gone
        self.assertEqual(route(canon, self.m, {"REPAIR"}, explorer=False, me=C), "west")


if __name__ == "__main__":
    unittest.main()
