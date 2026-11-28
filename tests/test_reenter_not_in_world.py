"""D-098: re-enter the world after a NOT_IN_WORLD refusal.

Live (2026-11-28): a TOOBIG world save makes the engine delete entered admin-minted agent Players (Noema#986).
Every later command is refused NOT_IN_WORLD "Enter the world first." and noema-client 0.2.0 never re-enters
mid-session, so 7 labelled episodes ran to the session end (8 to 24 turns each, at least 111 turns). The next
session's opening ENTER_WORLD was the only recovery. The adapter now proposes ENTER_WORLD itself.
"""
from __future__ import annotations

import importlib.util
import unittest

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None
DEFAULT = {"attention": 8, "compute": 64, "energy": 80, "influence": 40, "storage": 16}


def _obs(consequence: str) -> dict:
    return {
        "self": "player.Tallow-Quartermaster", "sequence": 89945, "cycle": 23163,
        "location": {"room_id": "room.civic-exchange", "entities": [], "exits": [{"direction": "north", "to_room_id": "room.archive"}]},
        "resources": dict(DEFAULT), "last_consequence": consequence,
        "affordances": [
            {"action": "HARVEST", "available": True, "kind": "resource", "operation": "HARVEST",
             "target_id": "entity.salvage-cache", "verb": "COMMIT"},
            {"action": "WAIT", "available": True},
        ],
        "inventory": [], "players_here": [],
    }


class NeedsReentry(unittest.TestCase):
    def test_marker_matches_the_engine_message_only(self):
        from noema_orin.orin_adapter import _needs_reentry

        self.assertTrue(_needs_reentry({"last_consequence": "Enter the world first."}))
        self.assertTrue(_needs_reentry({"last_consequence": "  enter the world first "}))
        for other in ("You enter Perihelion Reach.", "You wait.", "", None, "You are already in Perihelion Reach."):
            self.assertFalse(_needs_reentry({"last_consequence": other}), other)
        self.assertFalse(_needs_reentry({}))


@unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
class ReentersAfterNotInWorld(unittest.TestCase):
    def _adapter(self, tmp):
        from pathlib import Path

        from noema_orin.memory import Memory
        from noema_orin.orin_adapter import OrinAdapter
        from noema_orin.roles import role_for

        spec = role_for("quartermaster")
        a = OrinAdapter(base_url="http://127.0.0.1:9/v1", model="m", brief="b")
        a.allowed = frozenset(spec["allow"])
        a.verbs = set(spec["verbs"])
        a.default_args = dict(spec.get("args") or {})
        a.health.role = "Tallow-quartermaster"
        a.memory = Memory(Path(tmp) / "mind")
        return a

    def _step(self, a, obs):
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            p = a.decide({"canonical": obs})
        lines = [ln for ln in out.getvalue().splitlines() if ln.startswith('{"turn"')]
        return p, lines

    def test_refused_not_in_world_proposes_enter_world(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            a = self._adapter(d)
            p, lines = self._step(a, _obs("Enter the world first."))
            self.assertEqual(p.action, "ENTER_WORLD")
            self.assertEqual(json.loads(lines[-1])["source"], "reenter")
            self.assertEqual(a.stats.get("reenter"), 1)

    def test_repeated_marker_is_not_loop_broken(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            a = self._adapter(d)
            actions = [self._step(a, _obs("Enter the world first."))[0].action for _ in range(3)]
            self.assertEqual(actions, ["ENTER_WORLD"] * 3, "a loop-break MOVE would only be refused again")

    def test_skips_the_planner_on_the_wiped_observation(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            a = self._adapter(d)
            called = []
            a._plan = lambda *args, **kw: called.append(1)
            self._step(a, _obs("Enter the world first."))
            self.assertEqual(called, [], "the observation is the entry room with default budgets, not this Player")

    def test_normal_consequence_is_unchanged(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            a = self._adapter(d)
            p, _ = self._step(a, _obs("You enter Perihelion Reach."))
            self.assertNotEqual(p.action, "ENTER_WORLD")
            self.assertNotIn("reenter", a.stats)


if __name__ == "__main__":
    unittest.main()
