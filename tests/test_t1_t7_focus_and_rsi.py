"""T1 (#155) dual-track FOCUS and T7 (#161) RSI knob/trait/epoch wiring tests."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from noema_orin.persona import SEEDS, load_or_seed
from noema_orin.planner import focus
from noema_orin.roles import role_for
from noema_orin.rsi import RsiRatchet, load_agenda, maybe_revert_persona_on_epoch, save_agenda

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None


class DualTrackFocusTests(unittest.TestCase):
    def test_role_focus_tracks_defined_per_rfc0141_and_rfc0144(self):
        self.assertEqual(role_for("custodian")["focus_tracks"], ("engineer", "artificer"))
        self.assertEqual(role_for("archivist")["focus_tracks"], ("archivist", "surveyor"))
        self.assertEqual(role_for("surveyor")["focus_tracks"], ("explorer", "surveyor"))
        self.assertEqual(role_for("speaker")["focus_tracks"], ("herald",))

    def test_focus_allows_second_desired_track_and_blocks_after_cap(self):
        opts = [
            {"action": "FOCUS", "raw": {"track": "engineer", "cmd": "focus engineer"}},
            {"action": "FOCUS", "raw": {"track": "artificer", "cmd": "focus artificer"}},
            {"action": "FOCUS", "raw": {"track": "broker", "cmd": "focus broker"}},
            {"action": "LOOK"},
        ]
        # Holding 1 of 2 desired tracks keeps only the missing desired track (artificer)
        after_one = focus(opts, {"FOCUS", "REPAIR"}, held_tracks=["engineer"], desired_tracks=("engineer", "artificer"))
        self.assertEqual([o["raw"]["track"] for o in after_one if o["action"] == "FOCUS"], ["artificer"])
        # Holding both desired tracks drops all FOCUS options
        after_two = focus(
            opts,
            {"FOCUS", "REPAIR"},
            held_tracks=["engineer", "artificer"],
            desired_tracks=("engineer", "artificer"),
        )
        self.assertFalse(any(o["action"] == "FOCUS" for o in after_two))

    def test_agenda_migrates_legacy_held_track_and_caps_at_two(self):
        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            (mind / "agenda.json").write_text(json.dumps({"held_track": "engineer", "epoch": 1, "steps": []}))
            loaded = load_agenda(mind)
            self.assertEqual(loaded["held_tracks"], ["engineer"])
            self.assertEqual(loaded["held_track"], "engineer")

            save_agenda(mind, {"held_tracks": ["engineer", "artificer", "surveyor"], "epoch": 2, "steps": []})
            reloaded = load_agenda(mind)
            self.assertEqual(reloaded["held_tracks"], ["artificer", "surveyor"])
            self.assertEqual(reloaded["held_track"], "surveyor")


class DeadRsiAndTraitWiringTests(unittest.TestCase):
    def test_epoch_rollover_mean_reverts_persona_toward_seed(self):
        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            persona = load_or_seed(mind, "surveyor")
            persona["traits"]["caution"] = round(SEEDS["surveyor"]["traits"]["caution"] + 0.25, 3)
            ratchet = RsiRatchet(mind)
            # Epoch 0 -> 0: no reversion
            p_same, changed0 = maybe_revert_persona_on_epoch(mind, persona, ratchet, cycle=10)
            self.assertFalse(changed0)
            self.assertEqual(p_same["traits"]["caution"], persona["traits"]["caution"])
            # Epoch 0 -> 1 (cycle 40): mean-reverts toward seed and advances last_epoch
            p_next, changed1 = maybe_revert_persona_on_epoch(mind, persona, ratchet, cycle=40)
            self.assertTrue(changed1)
            self.assertLess(p_next["traits"]["caution"], persona["traits"]["caution"])
            self.assertEqual(ratchet.state["last_epoch"], 1)

    @unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
    def test_reflect_prompt_includes_rfc0141_knobs(self):
        from noema_orin.orin_adapter import OrinAdapter, reflect

        ad = OrinAdapter(base_url="http://127.0.0.1:9/v1", model="m", brief="b")
        captured = {}

        def fake_cloud(system: str, user: str):
            captured["system"] = system
            return {"knob_deltas": {"shop_margin_bias": 1}}

        persona = {"name": "Tallow", "role": "quartermaster", "traits": {"thrift": 0.9}, "quirk": "counts", "lessons": []}
        with patch("noema_orin.orin_adapter._cloud_reflect", side_effect=fake_cloud):
            out = reflect(ad, persona, [])
        self.assertEqual(out, {"knob_deltas": {"shop_margin_bias": 1}})
        for knob in ("tool_repair_floor", "battery_reserve_target", "shop_margin_bias"):
            self.assertIn(knob, captured["system"])

    @unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
    def test_social_outreach_cooldown_and_traits_modulate_adapter(self):
        from noema_orin.orin_adapter import OrinAdapter

        ad = OrinAdapter(base_url="http://127.0.0.1:9/v1", model="m", brief="b")
        ad.allowed = frozenset(role_for("speaker")["allow"])
        ad.verbs = set(role_for("speaker")["verbs"])
        ad.policy_knobs = {"social_outreach_cooldown": 10, "inspect_novelty_weight": 0.9}
        ad.persona_traits = {"sociability": 0.2, "caution": 0.9, "curiosity": 0.9, "thrift": 0.9}
        # Effective cooldown grows for low sociability; social outreach is suppressed right after a send
        self.assertGreaterEqual(ad._effective_social_cooldown(), 10)
        ad._last_social_turn = 5
        self.assertFalse(ad._social_outreach_ready(current_turn=8))
        self.assertTrue(ad._social_outreach_ready(current_turn=25))
        # High caution raises effective energy reserve floor; high thrift raises treasury build floor
        self.assertGreater(ad._effective_energy_floor(), 2)
        self.assertGreater(ad._effective_treasury_floor(), 12)


if __name__ == "__main__":
    unittest.main()
