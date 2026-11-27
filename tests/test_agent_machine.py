"""AGENTS.md workflow block must match .agents/machine.json, and the machine must be valid."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AgentMachineTest(unittest.TestCase):
    def test_machine_valid_and_agents_md_in_sync(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / ".agents" / "machine.py"), "check"], capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
