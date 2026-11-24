import json
import unittest
from types import SimpleNamespace as NS

from noema_orin.telemetry import rejection_summary, stop_detail


class TelemetryTests(unittest.TestCase):
    def test_counts_by_verb_and_code_with_keys_only(self):
        turns = [
            NS(ok=True),
            NS(ok=False, reason=None, failure=None, proposal=NS(action="org_office_assign", arguments={"office_id": "office.x", "agent_id": "player.secret"}),
               result=NS(error={"code": "INVALID_REQUEST", "message": "agent_id required"})),
            NS(ok=False, reason="STALE_HEAD", failure=None, proposal=NS(action="REPAIR", arguments={}), result=None),
            NS(ok=False, reason=None, failure=None, proposal=NS(action="ORG_OFFICE_ASSIGN", arguments={"office_id": "o"}),
               result=NS(error={"code": "INVALID_REQUEST"})),
        ]
        out = rejection_summary(turns)
        self.assertEqual(out["by_verb_code"], {"ORG_OFFICE_ASSIGN:INVALID_REQUEST": 2, "REPAIR:STALE_HEAD": 1})
        self.assertEqual(out["arg_keys"]["ORG_OFFICE_ASSIGN:INVALID_REQUEST"], ["agent_id", "office_id"])
        blob = json.dumps(out)
        self.assertNotIn("player.secret", blob)
        self.assertNotIn("required", blob)

    def test_stop_detail(self):
        self.assertEqual(stop_detail(NS(detail="INVALID_PROPOSAL")), "INVALID_PROPOSAL")
        self.assertIsNone(stop_detail(NS(detail=None)))


if __name__ == "__main__":
    unittest.main()
