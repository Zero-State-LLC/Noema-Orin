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
