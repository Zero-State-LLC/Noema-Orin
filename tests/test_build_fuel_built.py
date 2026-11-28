"""D-094: never wait or carry fuel for a treasury build the menu will not offer.

Live evidence (2026-11-28, m02 on 2b619de): 21 WAIT_TREASURY_BUILD_FUEL and 7 COLLECT_BUILD_FUEL of 39 planner
turns, and every remaining reversal was COLLECT_BUILD_FUEL out then SEEK_CUSTODIAN back. m02's memory records all
three of its build classes (generator, storage_bay, barter_stall) as built, so `prefer_builds` drops those
CONSTRUCTs from the menu and D-061 can never fire. D-062/D-063 still matched the raw affordances, so the
quartermaster waited beside, and walked back to, builds it would never make.
"""
from __future__ import annotations

import importlib.util
import unittest

from noema_orin.orin_adapter import _options
from noema_orin.roles import role_for

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None
BUILT_ALL = {"generator", "storage_bay", "barter_stall"}


def _blocked_build(cls="generator"):
    return {"action": "BUILD", "verb": "BUILD", "operation": "CONSTRUCT", "class": cls, "acting_for": "org.c",
            "office_id": "office.c.1", "available": False, "reason": "You do not have enough resources to construct."}


@unittest.skipUnless(_HAS_CLIENT, "requires noema_client")
class BuildFuelRespectsBuiltClasses(unittest.TestCase):
    def _qm(self, built=frozenset()):
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        spec = role_for("quartermaster")
        a.allowed, a.cohort_ids, a.role_handles = frozenset(spec["allow"]), set(), {}
        a.builds, a.supply, a.verbs = tuple(spec.get("builds") or ()), spec.get("supply"), set(spec["verbs"])
        a.memory, a.world_map, a.dwell, a.explorer, a.default_args, a.stats_mem = None, None, 0, False, {}, 0
        a.recent = []
        a._built_classes = lambda: set(built)
        return a

    def _canon(self, room="room.hall", storage_aboard=14, energy=2):
        return {"resources": {"energy": energy, "attention": 8, "storage": storage_aboard},
                "location": {"room_id": room, "exits": [{"to_room_id": "room.hall", "direction": "north"},
                                                        {"to_room_id": "room.x", "direction": "south"}]},
                "organizations": [{"org_id": "org.c", "treasury": {"storage": 61}}],
                "affordances": [_blocked_build("generator"), _blocked_build("storage_bay")]}

    def test_no_fuel_wait_for_a_class_already_built(self):
        a = self._qm(BUILT_ALL)
        c = self._canon()
        p = a._plan({"canonical": c}, a._menu({"canonical": c}))
        self.assertNotEqual(a.last_playbook_state, "WAIT_TREASURY_BUILD_FUEL")
        self.assertFalse(p is not None and p.action == "WAIT" and a.last_playbook_state == "WAIT_TREASURY_BUILD_FUEL")

    def test_still_waits_for_an_unbuilt_class(self):
        """D-062 unchanged: generator built, storage_bay not: wait for the storage_bay build."""
        a = self._qm({"generator", "barter_stall"})
        c = self._canon()
        p = a._plan({"canonical": c}, a._menu({"canonical": c}))
        self.assertEqual((a.last_playbook_state, p.action), ("WAIT_TREASURY_BUILD_FUEL", "WAIT"))

    def test_no_walk_back_to_a_build_room_when_every_class_is_built(self):
        """D-063's return leg: a remembered build room no longer pulls the quartermaster back."""
        import tempfile
        from pathlib import Path

        from noema_orin.memory import WorldMap

        a = self._qm(BUILT_ALL)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        a.world_map = WorldMap(Path(tmp.name))
        a.world_map.observe("room.hall", "Hall", 1, ["room.x"], [])
        a.world_map.observe("room.x", "X", 2, ["room.hall"], ["HARVEST"])
        a.build_room = "room.hall"
        c = self._canon(room="room.x", storage_aboard=10, energy=9)  # 6 cargo aboard, energy for a move
        c["affordances"] = []
        p = a._plan({"canonical": c}, _options(c, a.allowed))
        self.assertNotEqual(a.last_playbook_state, "COLLECT_BUILD_FUEL")
        self.assertIsNone(a.build_room, "a stale build room is dropped once no role class is left to build")
        del p

    def test_fuel_run_still_returns_for_an_unbuilt_class(self):
        import tempfile
        from pathlib import Path

        from noema_orin.memory import WorldMap

        a = self._qm({"generator"})
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        a.world_map = WorldMap(Path(tmp.name))
        a.world_map.observe("room.hall", "Hall", 1, ["room.x"], [])
        a.world_map.observe("room.x", "X", 2, ["room.hall"], ["HARVEST"])
        a.build_room = "room.hall"
        c = self._canon(room="room.x", storage_aboard=10, energy=9)
        c["affordances"] = []
        p = a._plan({"canonical": c}, _options(c, a.allowed))
        self.assertEqual((a.last_playbook_state, p.action, p.target_id), ("COLLECT_BUILD_FUEL", "MOVE", "north"))


if __name__ == "__main__":
    unittest.main()
