"""AGENTS.md workflow block, procedures and gate lifecycle must match .agents/*.json."""

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _docs():
    spec = importlib.util.spec_from_file_location("docs_machine", ROOT / ".agents" / "docs.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["docs_machine"] = mod
    spec.loader.exec_module(mod)
    return mod


class AgentMachineTest(unittest.TestCase):
    def test_machine_valid_and_agents_md_in_sync(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / ".agents" / "machine.py"), "check"], capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_procedures_gates_and_vendored_skills(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / ".agents" / "docs.py"), "check"], capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_gate_states_only_move_forward(self):
        d = _docs()
        gate = __import__("json").loads((ROOT / ".agents" / "lifecycles.json").read_text())["kinds"]["gate"]
        text = "## G-009: Example gate, NOT_COMPUTABLE\n"
        self.assertEqual(d.normalize(d.entries(gate, text)["G-009"], gate), "NOT_COMPUTABLE")
        self.assertTrue(d.forward(gate, "BLOCKED", "APPROVED"))
        self.assertFalse(d.forward(gate, "APPROVED", "BLOCKED"))


if __name__ == "__main__":
    unittest.main()
