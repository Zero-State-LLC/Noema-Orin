import unittest

from noema_orin.model_tier import tier_for
from noema_orin.orin_adapter import _depleted


class ModelTier(unittest.TestCase):
    def test_routine_menu_is_cheap(self):
        self.assertEqual(tier_for([{"action": "HARVEST"}, {"action": "WAIT"}, {"action": "MOVE"}]), "cheap")

    def test_any_org_or_social_option_is_strong(self):
        self.assertEqual(tier_for([{"action": "WAIT"}, {"action": "ORG_OFFICE_ASSIGN"}]), "strong")
        self.assertEqual(tier_for([{"action": "MESSAGE"}]), "strong")

    def test_unknown_or_empty_is_strong(self):
        self.assertEqual(tier_for([]), "strong")
        self.assertEqual(tier_for([{"action": "UPGRADE"}]), "strong")


class Depleted(unittest.TestCase):
    def test_zero_energy_any_hold(self):
        self.assertTrue(_depleted({"resources": {"energy": 0, "storage": 16}}))
        self.assertTrue(_depleted({"resources": {"energy": 0, "storage": 9}}))
        self.assertFalse(_depleted({"resources": {"energy": 1}}))
        self.assertFalse(_depleted({}))


class HarvestAmount(unittest.TestCase):
    def _p(self):
        from noema_client.types import ActionProposal
        return ActionProposal(action="HARVEST", target_id="e.cache", arguments={"operation": "HARVEST", "amount": 1})

    def test_bulk_bounded_by_cap_storage_stock(self):
        from noema_orin.orin_adapter import HARVEST_MAX, _harvest_amount
        c = {"resources": {"storage": 16}, "location": {"entities": [{"entity_id": "e.cache", "stock_amount": 9999}]}}
        self.assertEqual(_harvest_amount(self._p(), c).arguments["amount"], HARVEST_MAX)
        c["resources"]["storage"] = 3
        self.assertEqual(_harvest_amount(self._p(), c).arguments["amount"], 3)
        c["location"]["entities"][0]["stock_amount"] = 1.9
        self.assertEqual(_harvest_amount(self._p(), c).arguments["amount"], 1)

    def test_unknown_stock_left_alone(self):
        from noema_orin.orin_adapter import _harvest_amount
        self.assertEqual(_harvest_amount(self._p(), {"resources": {"storage": 16}}).arguments["amount"], 1)


class WaitRefuels(unittest.TestCase):
    def test_energy_one_empty_hold_does_not_wait_for_energy(self):
        from noema_orin.orin_adapter import _starved_for_attention
        c = {"resources": {"energy": 1, "storage": 16, "attention": 8},
             "affordances": [{"action": "HARVEST", "available": False, "requires": {"energy": 2},
                              "reason": "You need energy 2 and compute 1 to harvest."}]}
        self.assertFalse(_starved_for_attention(c, {"HARVEST"}))
        c["resources"]["storage"] = 12  # cargo aboard: WAIT burns it for +2
        self.assertTrue(_starved_for_attention(c, {"HARVEST"}))


class OfferedHere(unittest.TestCase):
    def test_unaffordable_role_verb_still_counts_as_here(self):
        from noema_orin.orin_adapter import _offered_here
        c = {"affordances": [{"action": "HARVEST", "available": False}, {"action": "LOOK"}]}
        self.assertTrue(_offered_here(c, {"HARVEST"}))
        self.assertFalse(_offered_here(c, {"REPAIR"}))
