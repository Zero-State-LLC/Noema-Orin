"""D-097: a CONVERT the engine offers carries `convert_mode`, which noema-client 0.2.0 does not copy into the proposal.

Live (2026-11-28, m02 after the D-094 rollout): CONVERT was sent with arguments {kind, operation} only, and the engine
refused it every time with INVALID_REQUEST "convert_mode must be power or compute" (world-actions.ts). The affordance
said `convert_mode: "power"`; `noema_client.affordances.ARGUMENT_KEYS` has no `convert_mode`, so it was dropped.
11 CONVERTs were sent fleet-wide across the logs.
"""
from __future__ import annotations

import importlib.util
import unittest

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None
AFF = {"action": "CONVERT", "available": True, "cmd": "convert power", "convert_mode": "power", "kind": "resource",
       "label": "Convert cargo to power", "operation": "CONVERT", "requires": {"compute": 1}, "verb": "COMMIT"}


@unittest.skipUnless(_HAS_CLIENT, "requires noema_client")
class ConvertCarriesItsMode(unittest.TestCase):
    def test_convert_proposal_carries_convert_mode(self):
        from noema_orin.orin_adapter import _proposal

        p = _proposal({"action": "CONVERT", "raw": AFF}, {})
        self.assertEqual((p.action, (p.arguments or {}).get("convert_mode")), ("CONVERT", "power"))

    def test_mode_from_cmd_when_the_field_is_missing(self):
        from noema_orin.orin_adapter import _proposal

        raw = {k: v for k, v in AFF.items() if k != "convert_mode"}
        raw["cmd"] = "convert compute"
        p = _proposal({"action": "CONVERT", "raw": raw}, {})
        self.assertEqual((p.arguments or {}).get("convert_mode"), "compute")

    def test_other_actions_unchanged(self):
        from noema_orin.orin_adapter import _proposal

        p = _proposal({"action": "HARVEST", "raw": {"action": "HARVEST", "operation": "HARVEST", "kind": "resource",
                                                     "target_id": "entity.node", "available": True}}, {})
        self.assertNotIn("convert_mode", p.arguments or {})


if __name__ == "__main__":
    unittest.main()
