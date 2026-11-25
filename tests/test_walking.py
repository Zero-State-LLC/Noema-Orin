"""S3-S6: walking waste. Nearest goal room, stay beside unaffordable role work, explorer energy floor."""
import tempfile
import unittest
from pathlib import Path

from noema_orin.memory import WorldMap
from noema_orin.orin_adapter import _budget_blocked, _energy_after_move_ok, _offered_here


class NearestGoalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.map = WorldMap(Path(self.tmp.name))
        # a - b - c ; far room seen last
        self.map.observe("room.c", "C", 5, ["room.b"], ["REPAIR"])
        self.map.observe("room.b", "B", 6, ["room.a", "room.c"], ["MOVE"])
        self.map.observe("room.a", "A", 7, ["room.b", "room.far"], ["MOVE"])
        self.map.observe("room.far", "Far", 9, ["room.a"], [])
        self.map.observe("room.d", "D", 10, ["room.e"], ["REPAIR"])  # newest but unreachable from a

    def tearDown(self):
        self.tmp.cleanup()

    def test_nearest_beats_most_recent(self):
        self.assertEqual(self.map.where_offered({"REPAIR"}, exclude="room.a", near="room.a"), "room.c")

    def test_without_near_keeps_recency(self):
        self.assertEqual(self.map.where_offered({"REPAIR"}), "room.d")

    def test_offer_no_longer_advertised_is_dropped(self):
        self.map.observe("room.c", "C", 11, ["room.b"], ["MOVE"])
        self.assertEqual(self.map.where_offered({"REPAIR"}, exclude="room.a", near="room.a"), "room.d")


class StayAndFloorTests(unittest.TestCase):
    def test_depleted_node_is_not_work_here(self):
        stock = {"operation": "HARVEST", "available": False, "reason": "Not enough stock available."}
        energy = {"operation": "HARVEST", "available": False, "reason": "You need energy 2 and compute 1 to harvest."}
        self.assertFalse(_budget_blocked(stock))
        self.assertFalse(_offered_here({"affordances": [stock]}, {"HARVEST"}))
        self.assertTrue(_offered_here({"affordances": [energy]}, {"HARVEST"}))

    def test_explorer_waits_below_two(self):
        self.assertFalse(_energy_after_move_ok({"resources": {"energy": 1}}, explorer=True))
        self.assertTrue(_energy_after_move_ok({"resources": {"energy": 2}}, explorer=True))
        self.assertTrue(_energy_after_move_ok({"resources": {"energy": 1}}, explorer=False))


if __name__ == "__main__":
    unittest.main()
