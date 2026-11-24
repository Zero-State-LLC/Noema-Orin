import unittest

from noema_orin.orin_adapter import _hold_empty, _starved_for_attention
from noema_orin.roles import role_for


class SupplyTests(unittest.TestCase):
    def test_custodian_may_harvest_for_materials(self):
        spec = role_for("custodian")
        self.assertIn("HARVEST", spec["allow"])
        self.assertNotIn("HARVEST", spec["verbs"])

    def test_hold_empty_matches_engine_capacity(self):
        self.assertTrue(_hold_empty({"resources": {"storage": 16}}))
        self.assertFalse(_hold_empty({"resources": {"storage": 14}}))
        self.assertFalse(_hold_empty({}))


class AttentionTests(unittest.TestCase):
    AFF = {"operation": "RECONSTRUCT", "available": False, "requires": {"attention": 2, "compute": 1},
           "reason": "You do not have enough attention."}

    def test_starved_when_role_verb_blocked_by_attention(self):
        self.assertTrue(_starved_for_attention({"resources": {"attention": 0}, "affordances": [self.AFF]}, {"RECONSTRUCT"}))

    def test_not_starved_for_other_roles_or_other_reasons(self):
        self.assertFalse(_starved_for_attention({"resources": {"attention": 0}, "affordances": [self.AFF]}, {"REPAIR"}))
        other = {**self.AFF, "reason": "You do not have materials in hold."}
        self.assertFalse(_starved_for_attention({"resources": {"attention": 0}, "affordances": [other]}, {"RECONSTRUCT"}))
        self.assertFalse(_starved_for_attention({"resources": {"attention": 4}, "affordances": [self.AFF]}, {"RECONSTRUCT"}))


if __name__ == "__main__":
    unittest.main()


class RoleSpaceTests(unittest.TestCase):
    def test_custodian_prefers_unbuilt_role_spaces(self):
        from noema_orin.planner import prefer_builds
        mk = lambda c: {"action": "CONSTRUCT", "raw": {"class": c}}
        opts = [mk("relay"), {"action": "HARVEST"}, mk("archive_annex"), mk("workshop")]
        out = prefer_builds(opts, ("workshop", "archive_annex"), set())
        self.assertEqual([o.get("raw", {}).get("class") or o["action"] for o in out], ["workshop", "archive_annex", "HARVEST"])
        out = prefer_builds(opts, ("workshop", "archive_annex"), {"workshop"})
        self.assertEqual([o.get("raw", {}).get("class") or o["action"] for o in out], ["archive_annex", "HARVEST"])


class HoldTests(unittest.TestCase):
    def test_hold_ready_at_six_materials(self):
        from noema_orin.orin_adapter import _hold_ready
        self.assertTrue(_hold_ready({"resources": {"storage": 5}}))
        self.assertFalse(_hold_ready({"resources": {"storage": 12}}))
