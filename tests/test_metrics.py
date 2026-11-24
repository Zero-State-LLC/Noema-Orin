import json
import tempfile
import unittest
from pathlib import Path

from noema_orin.metrics import collect, digest, open_db


LOG = [
    {"member": "m03", "stagger_offset_s": 16.0},
    {"member": "m03", "role": "custodian", "persona": "Rivet", "persona_version": 2},
    {"turn": 1, "source": "model", "action": "HARVEST"},
    {"turn": 2, "source": "planner", "action": "CONSTRUCT"},
    {"turn": 3, "source": "model", "action": "LOOK"},
    {"member": "m03", "transport_drop": "ConnectionError"},
    {"member": "m03", "role": "custodian", "actions": 3, "stop_reason": "validation_rejection", "stop_detail": "INVALID_PROPOSAL",
     "rejections": {"by_verb_code": {"REPAIR:INVALID_PROPOSAL": 1}}},
    {"turn": 4, "source": "model", "action": "REPAIR"},
    {"member": "m03", "role": "custodian", "actions": 1, "stop_reason": "duration_elapsed"},
]


class MetricsTests(unittest.TestCase):
    def test_collect_is_incremental_and_digest_rates(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "logs").mkdir()
            log = root / "logs" / "noema-player@m03.log"
            log.write_text("\n".join(json.dumps(x) for x in LOG) + "\nTraceback junk\n")
            db = open_db(root)
            self.assertEqual(collect(root, db), 2)
            self.assertEqual(collect(root, db), 0)
            out = digest(db)["members"]["m03"]
            self.assertEqual((out["sessions"], out["full_sessions"], out["turns"], out["drops"]), (2, 1, 4, 1))
            self.assertEqual(out["role_action_rate"], 0.5)  # CONSTRUCT + REPAIR of 4 (HARVEST is supply)
            db.close()


if __name__ == "__main__":
    unittest.main()
