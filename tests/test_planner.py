import tempfile
import unittest
from pathlib import Path

from noema_orin.memory import WorldMap
from noema_orin.planner import facts_from, home_org, refine, route
from noema_orin.players import cohort_ids, record_self, stagger


def org(oid, cycle, members=("player.f",)):
    return {"org_id": oid, "my_role": "founder", "created_cycle": cycle, "members": [{"agent_id": m} for m in members]}


CANON = {
    "organizations": [org("org.b", 20), org("org.a", 10)],
    "players_here": [{"player_id": "player.q", "handle": "q"}, {"player_id": "player.stranger", "handle": "stranger"}],
    "location": {"room_id": "room.civic", "name": "Civic", "condition": "damaged",
                 "exits": [{"direction": "north", "to_room_id": "room.relay"}, {"direction": "east", "to_room_id": "room.ring"}]},
    "affordances": [{"action": "HARVEST", "available": True}, {"action": "TRADE", "available": False}],
    "sequence": 7,
}


class PlannerTests(unittest.TestCase):
    def test_home_org_is_oldest_founded(self):
        self.assertEqual(home_org(CANON), "org.a")

    def test_refine_drops_duplicate_create_foreign_org_acts_and_non_cohort_invites(self):
        opts = [{"action": "ORG_CREATE"}, {"action": "ORG_OFFICE_CREATE", "target_id": "org.b"},
                {"action": "ORG_OFFICE_CREATE", "target_id": "org.a"},
                {"action": "ORG_INVITE", "target_id": "org.a", "target_label": "stranger"},
                {"action": "ORG_INVITE", "target_id": "org.a", "target_label": "q"}, {"action": "LOOK"}]
        out = refine(opts, CANON, {"player.q"})
        self.assertEqual([(o["action"], o.get("target_label")) for o in out],
                         [("ORG_INVITE", "q"), ("ORG_OFFICE_CREATE", None), ("LOOK", None)])
        self.assertEqual([o["i"] for o in out], [0, 1, 2])

    def test_route_toward_room_offering_role_verb(self):
        with tempfile.TemporaryDirectory() as d:
            m = WorldMap(Path(d))
            m.observe("room.civic", "Civic", 1, ["room.relay", "room.ring"], ["MOVE"])
            m.observe("room.relay", "Relay", 2, ["room.civic"], ["REPAIR"])
            self.assertEqual(route(CANON, m, {"REPAIR"}, explorer=False), "north")
            self.assertEqual(route(CANON, m, {"FOCUS"}, explorer=True), "east")

    def test_focus_hides_idle_when_role_verbs_offered(self):
        from noema_orin.planner import focus
        opts = [{"action": "LOOK"}, {"action": "REPAIR"}, {"action": "MOVE"}]
        self.assertEqual([o["action"] for o in focus(opts, {"REPAIR"})], ["REPAIR", "MOVE"])
        self.assertEqual(len(focus(opts, {"HARVEST"})), 3)

    def test_facts_are_observed_only(self):
        self.assertEqual(facts_from(CANON), [("room", "Civic: damaged"), ("offer", "Civic offers HARVEST")])


class CohortTests(unittest.TestCase):
    def test_stagger_spreads_starts_and_scales_cooldown(self):
        members = ["m01", "m02", "m03", "m04"]
        self.assertEqual(stagger(members, "m01", 20, 8), (32, 0.0))
        self.assertEqual(stagger(members, "m03", 20, 8), (32, 16.0))

    def test_cohort_ids_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            record_self(Path(d), "m01", "player.a")
            record_self(Path(d), "m02", "player.b")
            self.assertEqual(cohort_ids(Path(d)), {"player.a", "player.b"})


if __name__ == "__main__":
    unittest.main()
