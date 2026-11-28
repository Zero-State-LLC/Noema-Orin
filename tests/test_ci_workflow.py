"""CI workflow guards (D-087 amendment).

GitHub runs `run:` steps with `bash -e {0}`, which has no pipefail: the production-client suite pipes
unittest into `tee`, so a failing suite exited 0 through the pipe. The workflow now sets pipefail for
every step; this keeps it that way.
"""
import pathlib
import re
import unittest

CI = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"


class WorkflowShell(unittest.TestCase):
    def test_default_shell_sets_pipefail(self):
        text = CI.read_text()
        m = re.search(r"^defaults:\n  run:\n    shell: (.+)$", text, re.M)
        self.assertIsNotNone(m, "ci.yml must set defaults.run.shell")
        self.assertIn("pipefail", m.group(1))

    def test_no_step_overrides_the_shell_without_pipefail(self):
        for line in CI.read_text().splitlines():
            s = line.strip()
            if s.startswith("shell:") and "bash" in s:
                self.assertIn("pipefail", s, line)


if __name__ == "__main__":
    unittest.main()
