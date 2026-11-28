"""D-100: don't offer a CONVERT the hold can't feed, and don't loop-break into a LOOK at attention 0.

Live (2026-11-28 14:43Z to 18:57Z): m02 (quartermaster) sat in Relay Quarter at energy 1, attention 0, holding only
SALVAGE_COMPOSITE. The engine advertised "convert compute" as available (affordances check budgets only), so the model
sent CONVERT twice per session and the engine refused both, BUDGET_EXCEEDED "Convert compute requires 2 SILICA_CELL in
hold". The repeat triggered a loop break, which can't MOVE at energy 1 and fell back to LOOK, refused at attention 0.
Three refusals tripped the client's circuit breaker within the session's first 3 minutes, 108 sessions in a row:
231 refused CONVERTs and 109 refused LOOKs, 340 of the fleet's 3,580 labelled turns since 09:07Z. Replayed through
this code with m02's own memory and knobs, the same 326 observations give 326 WAITs (they refuel it).
"""
from __future__ import annotations

import importlib.util
import unittest

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None

CONVERT_COMPUTE = {"action": "CONVERT", "available": True, "cmd": "convert compute", "convert_mode": "compute",
                   "kind": "resource", "label": "Convert silica to compute", "operation": "CONVERT",
                   "requires": {"energy": 1}, "verb": "COMMIT"}
CONVERT_POWER = {**CONVERT_COMPUTE, "cmd": "convert power", "convert_mode": "power", "label": "Convert cargo to power",
                 "requires": {"compute": 1}}
STUCK = {"attention": 0, "compute": 61, "energy": 1, "influence": 40, "storage": 0}
SALVAGE = [{"amount": 35, "grade": "SOUND", "material": "SALVAGE_COMPOSITE", "origin_room_id": "room.civic-exchange"}]


def _canonical(lots, resources=None, affordances=None):
    return {"resources": dict(resources or STUCK), "material_lots": lots,
            "affordances": list(affordances or [CONVERT_COMPUTE, {"action": "WAIT", "available": True}]),
            "location": {"room_id": "room.relay-quarter", "exits": [
                {"direction": "south", "to_room_id": "room.civic-exchange"}]}}


class ConvertNeedsMaterial(unittest.TestCase):
    def test_compute_without_silica_is_not_offered(self):
        from noema_orin.orin_adapter import _convert_has_material

        self.assertFalse(_convert_has_material(CONVERT_COMPUTE, _canonical(SALVAGE)))
        self.assertFalse(_convert_has_material(CONVERT_COMPUTE, _canonical([])))
        one = [{"amount": 1, "grade": "SOUND", "material": "SILICA_CELL"}] + SALVAGE
        self.assertFalse(_convert_has_material(CONVERT_COMPUTE, _canonical(one)))

    def test_compute_with_two_silica_is_offered(self):
        from noema_orin.orin_adapter import _convert_has_material

        two = [{"amount": 1, "grade": "SOUND", "material": "SILICA_CELL"},
               {"amount": 1, "grade": "WORN", "material": "SILICA_CELL"}] + SALVAGE
        self.assertTrue(_convert_has_material(CONVERT_COMPUTE, _canonical(two)))

    def test_mode_read_from_cmd_when_the_field_is_missing(self):
        from noema_orin.orin_adapter import _convert_has_material

        raw = {k: v for k, v in CONVERT_COMPUTE.items() if k != "convert_mode"}
        self.assertFalse(_convert_has_material(raw, _canonical(SALVAGE)))

    def test_power_and_unknowns_stay_on_offer(self):
        from noema_orin.orin_adapter import _convert_has_material

        self.assertTrue(_convert_has_material(CONVERT_POWER, _canonical(SALVAGE)), "power can burn 3 untyped cargo")
        self.assertTrue(_convert_has_material(CONVERT_COMPUTE, {"resources": dict(STUCK)}), "no lot list observed")
        self.assertTrue(_convert_has_material(CONVERT_COMPUTE, _canonical([{"material": "SILICA_CELL"}])))
        self.assertTrue(_convert_has_material({**CONVERT_COMPUTE, "convert_mode": "?", "cmd": "convert"},
                                              _canonical(SALVAGE)))

    def test_menu_drops_the_convert_and_keeps_the_rest(self):
        from noema_orin.orin_adapter import _options
        from noema_orin.roles import role_for

        allowed = frozenset(role_for("quartermaster")["allow"])
        self.assertEqual([o["action"] for o in _options(_canonical(SALVAGE), allowed)], ["WAIT"])
        silica = [{"amount": 2, "grade": "SOUND", "material": "SILICA_CELL"}]
        self.assertEqual([o["action"] for o in _options(_canonical(silica), allowed)], ["CONVERT", "WAIT"])


@unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
class LoopBreakAffordsItsLook(unittest.TestCase):
    def _adapter(self):
        from noema_orin.orin_adapter import OrinAdapter

        a = OrinAdapter.__new__(OrinAdapter)
        a.world_map = None
        return a

    def test_no_look_at_attention_zero(self):
        a = self._adapter()
        self.assertEqual(a._loop_break_move({"canonical": _canonical(SALVAGE)}).action, "WAIT")

    def test_look_when_attention_allows(self):
        a = self._adapter()
        ctx = {"canonical": _canonical(SALVAGE, resources={**STUCK, "attention": 1})}
        self.assertEqual(a._loop_break_move(ctx).action, "LOOK")

    def test_stuck_turn_never_proposes_a_refused_convert_or_look(self):
        """decide() on m02's stuck observation, with the model and planner stubbed to the choices they made live."""
        import contextlib
        import io

        from noema_client.types import ActionProposal

        from noema_orin.orin_adapter import OrinAdapter
        from noema_orin.roles import role_for

        spec = role_for("quartermaster")
        a = OrinAdapter(base_url="http://127.0.0.1:9/v1", model="m", brief="b")
        a.allowed = frozenset(spec["allow"])
        a.verbs = set(spec["verbs"])
        a.supply = set(spec.get("supply") or ())
        a.default_args = dict(spec.get("args") or {})
        a._plan = lambda *_a, **_k: None
        seen_menus = []

        def ask(context, options):
            seen_menus.append([o["action"] for o in options])
            convert = next((o for o in options if o["action"] == "CONVERT"), None)
            return ActionProposal(action="CONVERT", arguments={"convert_mode": "compute"}) if convert else None

        a._ask = ask
        out = io.StringIO()
        actions = []
        with contextlib.redirect_stdout(out):
            for _ in range(3):
                actions.append(a.decide({"canonical": _canonical(SALVAGE)}).action)
        self.assertNotIn("CONVERT", actions)
        self.assertNotIn("LOOK", actions)
        self.assertTrue(all("CONVERT" not in m for m in seen_menus), seen_menus)

    def _fallback_adapter(self, generic_choice):
        from noema_orin.orin_adapter import OrinAdapter
        from noema_orin.roles import role_for

        spec = role_for("quartermaster")
        a = OrinAdapter(base_url="http://127.0.0.1:9/v1", model="m", brief="b")
        a.allowed = frozenset(spec["allow"])
        a.verbs = set(spec["verbs"])
        a.default_args = {}
        a.memory = None
        a.recent = [{"action": "WAIT", "target": None}]  # WAIT already tried: the generic adapter is asked

        class Generic:
            def decide(self, _context):
                return generic_choice

        a.fallback = Generic()
        return a

    def test_generic_fallback_convert_is_checked_like_the_menu(self):
        from noema_client.types import ActionProposal

        bare = ActionProposal(action="CONVERT", arguments={"kind": "resource", "operation": "CONVERT"})
        a = self._fallback_adapter(bare)
        out = a._role_fallback({"canonical": _canonical(SALVAGE)}, [])
        self.assertEqual(out.action, "WAIT", "no silica: the engine refuses it")
        silica = [{"amount": 2, "grade": "SOUND", "material": "SILICA_CELL"}]
        out = a._role_fallback({"canonical": _canonical(silica)}, [])
        self.assertEqual((out.action, (out.arguments or {}).get("convert_mode")), ("CONVERT", "compute"),
                         "sent with the convert_mode the generic proposal drops (D-097)")

    def test_generic_fallback_other_choices_unchanged(self):
        from noema_client.types import ActionProposal

        a = self._fallback_adapter(ActionProposal(action="WAIT"))
        self.assertEqual(a._role_fallback({"canonical": _canonical(SALVAGE)}, []).action, "WAIT")


if __name__ == "__main__":
    unittest.main()
