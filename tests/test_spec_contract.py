"""Static bootstrap checks; these do not validate runtime behavior or hardware."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SpecificationBootstrapTests(unittest.TestCase):
    def test_pocock_spec_sections(self):
        spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")
        for section in (
            "Problem Statement", "Solution", "User Stories",
            "Implementation Decisions", "Testing Decisions", "Out of Scope",
            "Further Notes",
        ):
            with self.subTest(section=section):
                self.assertIn(f"## {section}", spec)
        self.assertGreaterEqual(len(re.findall(r"(?m)^\d+\. As an? ", spec)), 10)

    def test_boundary_and_source_pins(self):
        spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")
        decisions = (ROOT / "DECISIONS.md").read_text(encoding="utf-8")
        self.assertIn("619d0674518761aa08462d3f5d5966a917259aa1", spec)
        self.assertIn("BLOCKED_SPEC_DEFECT", (ROOT / "execplan/01-foundation.md").read_text(encoding="utf-8"))
        for token in ("hosted", "offline-spark", "Noema-Specs", "BLOCKED"):
            with self.subTest(token=token):
                self.assertIn(token, decisions)

    def test_foundation_is_bounded_and_implementable(self):
        foundation = (ROOT / "SPEC-FOUNDATION.md").read_text(encoding="utf-8")
        plan = (ROOT / "execplan/01-foundation.md").read_text(encoding="utf-8")
        for section in ("Problem Statement", "Solution", "User Stories", "Implementation Decisions", "Testing Decisions", "Out of Scope", "Further Notes"):
            with self.subTest(section=section):
                self.assertIn(f"## {section}", foundation)
        for token in ("#1", "#2", "#3", "#4–#6", "BLOCKED_SPEC_DEFECT"):
            with self.subTest(token=token):
                self.assertIn(token, foundation + plan)
        for token in ("REFUSED", "FAILED_SUBMISSION", "ATTEMPTED", "before fixture loading", "exactly one", "no retry", "stdout", "stderr"):
            with self.subTest(outcome_contract=token):
                self.assertIn(token, foundation + plan)
        self.assertIn("GLOSSARY.md", foundation)
        self.assertIn("docs/adr/0001-synthetic-runner-output-boundary.md", foundation)
        glossary = (ROOT / "GLOSSARY.md").read_text(encoding="utf-8")
        for term in ("Target profile", "Submission attempt", "Refusal record", "Failed submission attempt", "Dry-run receipt", "Fixture observation"):
            with self.subTest(local_term=term):
                self.assertIn(f"**{term}**:", glossary)
        for section in ("Progress", "Surprises & Discoveries", "Decision Log", "Outcomes & Retrospective", "Validation and Acceptance"):
            with self.subTest(section=section):
                self.assertIn(f"## {section}", plan)

    def test_local_links_and_plan(self):
        for rel in ("README.md", "SPEC.md", "SPEC-FOUNDATION.md", "AGENTS.md", "DECISIONS.md", "GLOSSARY.md", "docs/adr/0001-synthetic-runner-output-boundary.md", "docs/agents/domain.md", "execplan/01-foundation.md"):
            with self.subTest(rel=rel):
                self.assertTrue((ROOT / rel).is_file())
        for rel in ("README.md", "SPEC.md", "SPEC-FOUNDATION.md", "docs/agents/domain.md"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if target.startswith(("http://", "https://", "#")):
                    continue
                with self.subTest(source=rel, target=target):
                    self.assertTrue((ROOT / rel).parent.joinpath(target.split("#")[0]).is_file())


if __name__ == "__main__":
    unittest.main()
