import unittest

from noema_orin.roles import DENY_ALWAYS, ROLES, role_for


class RoleTests(unittest.TestCase):
    def test_roster_matches_system_roles_doc(self):
        self.assertEqual(set(ROLES), {"founder", "quartermaster", "custodian", "archivist", "speaker", "spare", "maintenance"})

    def test_maintenance_matches_operator_contract(self):
        self.assertEqual(set(ROLES["maintenance"]["allow"]),
                         {"LOOK", "INSPECT", "WAIT", "ENTER_WORLD", "OBSERVE", "HARVEST", "COMMIT.HARVEST"})

    def test_no_role_may_trade_or_grant_access(self):
        for name, spec in ROLES.items():
            with self.subTest(role=name):
                self.assertFalse(set(spec["allow"]) & set(DENY_ALWAYS))

    def test_unknown_role_refuses(self):
        for bad in (None, "", "admin", "Quartermaster"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                role_for(bad)


if __name__ == "__main__":
    unittest.main()
