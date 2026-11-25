"""S11: the founder welcomes each non-cohort Player once."""
import tempfile
import unittest
from pathlib import Path

try:
    import noema_client  # noqa: F401
except ImportError:
    noema_client = None

from noema_orin.memory import Memory
from noema_orin.roles import role_for


@unittest.skipIf(noema_client is None, "needs noema_client")
class FounderWelcomeTests(unittest.TestCase):
    def test_once_per_player_and_never_cohort(self):
        from noema_orin.orin_adapter import OrinAdapter

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        a = OrinAdapter.__new__(OrinAdapter)
        spec = role_for("founder")
        a.verbs, a.cohort_ids = set(spec["verbs"]), {"player.Perigee-Surveyor"}
        a.memory = Memory(Path(tmp.name))
        c = {"organizations": [{"org_id": "org.c", "name": "Reach Compact", "my_role": "founder", "created_cycle": 1}]}
        opts = [{"action": "MESSAGE", "target_id": "player.Perigee-Surveyor"},
                {"action": "MESSAGE", "target_id": "player.visitor"}]
        p = a._welcome(c, opts)
        self.assertEqual((p.action, p.target_id), ("MESSAGE", "player.visitor"))
        self.assertIn("Reach Compact", p.arguments["text"])
        self.assertIsNone(a._welcome(c, opts))


if __name__ == "__main__":
    unittest.main()
