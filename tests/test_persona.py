import json
import tempfile
import unittest
from pathlib import Path

from noema_orin.persona import MAX_DRIFT, SEEDS, apply_reflection, handle_for, load_or_seed, prompt_block
from noema_orin.roles import BASE, DENY_ALWAYS, ROLES, role_for

CIVIC = ("founder", "quartermaster", "custodian", "archivist", "speaker", "surveyor")


class PersonaTests(unittest.TestCase):
    def test_every_role_has_a_unique_themed_name_and_handle_shows_name_and_role(self):
        names = [SEEDS[r]["name"] for r in CIVIC]
        self.assertEqual(len(set(names)), 6)
        for role in CIVIC:
            handle = handle_for(role)
            self.assertIn(SEEDS[role]["name"], handle)
            self.assertIn(role.capitalize(), handle)
            self.assertLessEqual(len(handle), 32)
            self.assertRegex(handle, r"^[A-Za-z0-9_-]+$")

    def test_reflection_drift_is_bounded_and_versioned(self):
        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            p = load_or_seed(mind, "surveyor")
            before = p["traits"]["caution"]
            p2, ok = apply_reflection(mind, p, {"trait_deltas": {"caution": 5}, "lesson": "Ring 3 is a dead end."})
            self.assertTrue(ok)
            self.assertAlmostEqual(p2["traits"]["caution"], round(before + MAX_DRIFT, 3))
            self.assertEqual(p2["version"], 2)
            self.assertTrue((mind / "persona.v1.json").is_file() and (mind / "persona.v2.json").is_file())
            self.assertEqual(json.loads((mind / "persona.json").read_text())["name"], "Perigee")

    def test_reflection_cannot_rename_or_change_role(self):
        with tempfile.TemporaryDirectory() as d:
            p = load_or_seed(Path(d), "founder")
            for bad in ({"name": "Admin"}, {"role": "maintenance"}, {"trait_deltas": {"power": 1}}, "x", None):
                with self.subTest(bad=bad):
                    out, ok = apply_reflection(Path(d), p, bad)
                    self.assertFalse(ok)
                    self.assertEqual(out, p)

    def test_prompt_names_persona_and_reach(self):
        with tempfile.TemporaryDirectory() as d:
            block = prompt_block(load_or_seed(Path(d), "archivist"))
            self.assertIn("Vellum", block)
            self.assertIn("Perihelion Reach", block)


class RoleVerbTests(unittest.TestCase):
    def test_each_civic_role_owns_unique_function_verbs(self):
        owned = {r: set(ROLES[r]["verbs"]) for r in CIVIC}
        for role, verbs in owned.items():
            others = set().union(*(v for k, v in owned.items() if k != role))
            with self.subTest(role=role):
                self.assertTrue(verbs - others, "role has no verb unique to its function")
                self.assertFalse(verbs & set(BASE))

    def test_denied_verbs_never_allowed(self):
        for role in ROLES:
            with self.subTest(role=role):
                self.assertFalse(set(role_for(role)["allow"]) & set(DENY_ALWAYS))


if __name__ == "__main__":
    unittest.main()
