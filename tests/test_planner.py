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

    def test_agreements_only_with_cohort_and_never_trade_or_access(self):
        mk = lambda t, p: {"action": "AGREEMENT_FORM", "target_id": p, "raw": {"agreement_type": t, "player_id": p}}
        opts = [mk("TRADE", "player.q"), mk("access", "player.q"), mk("defense", "player.stranger"), mk("defense", "player.q")]
        out = refine(opts, CANON, {"player.q"})
        self.assertEqual([(o["raw"]["agreement_type"], o["target_id"]) for o in out], [("defense", "player.q")])

    def test_no_duplicate_office(self):
        canon = {**CANON, "organizations": [{**org("org.a", 10), "offices": [{"display_name": "Notice"}]}]}
        opt = {"action": "ORG_OFFICE_CREATE", "target_id": "org.a", "raw": {"cmd": 'office create org.a name="Notice" profile=P'}}
        self.assertEqual(refine([opt], canon, set()), [])

    def test_without_home_org_only_founding_is_offered(self):
        canon = {**CANON, "organizations": []}
        out = refine([{"action": "LOOK"}, {"action": "ORG_CREATE"}, {"action": "ORG_CREATE"}], canon, set())
        self.assertEqual([o["action"] for o in out], ["ORG_CREATE"])

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


class PinnedHomeTests(unittest.TestCase):
    def tearDown(self):
        import noema_orin.planner as p
        p.PINNED_HOME = None

    def test_pinned_home_blocks_org_create_even_without_organizations(self):
        import noema_orin.planner as p
        canon = {"organizations": [], "players_here": []}
        self.assertEqual([o["action"] for o in refine([{"action": "ORG_CREATE"}], canon, set())], ["ORG_CREATE"])
        p.PINNED_HOME = "org.reach-compact.34df3bb5"
        self.assertEqual(refine([{"action": "ORG_CREATE"}, {"action": "LOOK"}], canon, set())[0]["action"], "LOOK")
        self.assertEqual(home_org(canon), "org.reach-compact.34df3bb5")
