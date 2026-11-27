"""C2 (#197): tabular consequence model fitted from transition rows. Stage 1 of Spec #194 (D-080)."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from noema_orin.consequence import NOT_COMPUTABLE, ConsequenceModel, features
from noema_orin.transitions import TransitionLog, iter_labelled

OK = {"ok": True}
NO = {"ok": False, "code": "BUDGET_EXCEEDED"}


def _obs(energy=5, room="room.a", entities=("e.relay",), affordances=None, **extra):
    return {"location": {"room_id": room, "entities": [{"entity_id": e} for e in entities]},
            "resources": {"energy": energy, "attention": 8, "compute": 5, "storage": 16, "influence": 0},
            "affordances": affordances if affordances is not None else [
                {"action": "REPAIR", "target_id": "e.relay", "available": True}, {"action": "MOVE", "available": True},
                {"action": "WAIT", "available": True}],
            **extra}


def _act(action, target=None):
    return {"action": action, "target_id": target, "arguments": {}}


class ConsequenceModelTests(unittest.TestCase):
    def test_learns_a_verb_that_is_rejected_below_an_energy_level(self):
        model = ConsequenceModel(min_support=5)
        for _ in range(8):
            for energy in (0, 1, 2):
                model.observe(_obs(energy), _act("REPAIR", "e.relay"), _obs(energy), NO)
            for energy in (3, 4, 6, 9):
                model.observe(_obs(energy), _act("REPAIR", "e.relay"), _obs(energy - 3), OK)
        low = model.predict(_obs(1), {"action": "REPAIR", "target_id": "e.relay"})
        high = model.predict(_obs(7), {"action": "REPAIR", "target_id": "e.relay"})
        self.assertEqual(low["label"], "INFERRED")
        self.assertGreater(low["rejected_p"], 0.8)
        self.assertLess(high["rejected_p"], 0.2)
        self.assertEqual(high["budget_delta"]["energy"], -3)

    def test_below_minimum_support_there_is_no_prediction(self):
        model = ConsequenceModel(min_support=5)
        for _ in range(4):
            model.observe(_obs(5), _act("REPAIR", "e.relay"), _obs(2), OK)
        got = model.predict(_obs(5), _act("REPAIR", "e.relay"))
        self.assertEqual(got["label"], NOT_COMPUTABLE)
        self.assertEqual(got["rejected_p"], NOT_COMPUTABLE)
        self.assertEqual(got["budget_delta"], NOT_COMPUTABLE)
        self.assertEqual(got["room_changes_p"], NOT_COMPUTABLE)
        self.assertEqual(model.predict(_obs(5), _act("TRADE"))["label"], NOT_COMPUTABLE)  # never seen at all

    def test_budget_change_is_a_median_and_room_change_is_a_frequency(self):
        model = ConsequenceModel(min_support=3)
        for delta in (-1, -1, -1, -1, -9):  # one outlier must not move the estimate
            model.observe(_obs(9), _act("MOVE", "north"), _obs(9 + delta, room="room.b"), OK)
        for _ in range(5):
            model.observe(_obs(1), _act("WAIT"), _obs(3), OK)
        move = model.predict(_obs(9), _act("MOVE", "north"))
        wait = model.predict(_obs(1), _act("WAIT"))
        self.assertEqual(move["budget_delta"]["energy"], -1)
        self.assertEqual(move["budget_delta"]["attention"], 0)
        self.assertGreater(move["room_changes_p"], 0.8)
        self.assertEqual(wait["budget_delta"]["energy"], 2)
        self.assertLess(wait["room_changes_p"], 0.2)

    def test_unlabelled_rows_inform_budgets_and_rooms_but_not_rejection(self):
        model = ConsequenceModel(min_support=3)
        for _ in range(6):
            model.observe(_obs(5), _act("WAIT"), _obs(7), None)
        got = model.predict(_obs(5), _act("WAIT"))
        self.assertEqual(got["label"], "INFERRED")
        self.assertEqual(got["rejected_p"], NOT_COMPUTABLE)
        self.assertEqual(got["budget_delta"]["energy"], 2)

    def test_a_turn_without_a_next_observation_informs_rejection_only(self):
        model = ConsequenceModel(min_support=3)
        for _ in range(6):
            model.observe(_obs(5), _act("WAIT"), None, OK)
        got = model.predict(_obs(5), _act("WAIT"))
        self.assertLess(got["rejected_p"], 0.2)
        self.assertEqual(got["budget_delta"], NOT_COMPUTABLE)

    def test_an_unseen_room_backs_off_to_a_coarser_key_and_says_so(self):
        model = ConsequenceModel(min_support=5)
        for i in range(10):
            model.observe(_obs(5, room=f"room.{i}"), _act("REPAIR", "e.relay"), _obs(2, room=f"room.{i}"), OK)
        seen_often = ConsequenceModel(min_support=5)
        for _ in range(10):
            seen_often.observe(_obs(5), _act("REPAIR", "e.relay"), _obs(2), OK)
        self.assertEqual(model.predict(_obs(5, room="room.new"), _act("REPAIR", "e.relay"))["basis"], "action+budget")
        self.assertEqual(seen_often.predict(_obs(5), _act("REPAIR", "e.relay"))["basis"], "action+budget+room")

    def test_features_use_only_the_coarse_context_and_never_message_text(self):
        base = _obs(5)
        noisy = _obs(5, world_text=["Vesper says: meet me at the vault"], last_consequence="You heard a report from x.",
                     players_here=[{"player_id": "player.other", "note": "private"}], rumor_lines=["a claim"])
        self.assertEqual(features(base, "REPAIR", "e.relay"), features(noisy, "REPAIR", "e.relay"))
        self.assertNotEqual(features(_obs(5), "REPAIR", "e.relay"), features(_obs(1), "REPAIR", "e.relay"))
        self.assertNotEqual(features(_obs(5), "REPAIR", "e.relay"), features(_obs(5, entities=()), "REPAIR", "e.relay"))
        unavailable = _obs(5, affordances=[{"action": "REPAIR", "target_id": "e.relay", "available": False}])
        self.assertNotEqual(features(_obs(5), "REPAIR", "e.relay"), features(unavailable, "REPAIR", "e.relay"))

    def test_key_count_is_bounded_and_coarse_keys_outlive_one_off_rooms(self):
        model = ConsequenceModel(min_support=5, max_keys=40)
        for i in range(500):
            model.observe(_obs(5, room=f"room.{i}"), _act("REPAIR", "e.relay"), _obs(2, room=f"room.{i}"), OK)
        self.assertLessEqual(model.key_count, 40)
        self.assertEqual(model.predict(_obs(5, room="room.zzz"), _act("REPAIR", "e.relay"))["budget_delta"]["energy"], -3)

    def test_predict_accepts_a_menu_option_or_a_proposal(self):
        model = ConsequenceModel(min_support=2)
        for _ in range(3):
            model.observe(_obs(5), _act("WAIT"), _obs(7), OK)
        option = {"i": 0, "action": "WAIT", "target_id": None, "raw": {"action": "WAIT"}}
        proposal = SimpleNamespace(action="wait", target_id=None, arguments=None)
        self.assertEqual(model.predict(_obs(5), option), model.predict(_obs(5), proposal))

    def test_malformed_observations_do_not_raise(self):
        model = ConsequenceModel(min_support=1)
        model.observe({}, {"action": None}, {"resources": "broken"}, {"ok": "yes"})
        model.observe({"resources": {"energy": "lots"}, "location": None, "affordances": [None, 3]}, _act("WAIT"), None, None)
        self.assertEqual(model.predict({}, {})["label"], NOT_COMPUTABLE)


class FitFromLogTests(unittest.TestCase):
    def test_fits_from_the_transition_log_with_outcomes(self):
        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            log = TransitionLog(mind)
            log.new_session()
            turns = []
            for i in range(12):
                energy = i % 6
                log.append(canonical=_obs(energy), proposal=SimpleNamespace(action="REPAIR", target_id="e.relay", arguments=None),
                           source="planner")
                ok = energy >= 3
                turns.append(SimpleNamespace(ok=ok, reason=None, failure=None,
                                             proposal=SimpleNamespace(action="REPAIR"),
                                             result=SimpleNamespace(ok=ok, error=None if ok else {"code": "BUDGET_EXCEEDED"})))
            log.record_outcomes(turns)
            rows = list(iter_labelled(mind))
            self.assertEqual(len(rows), 12)
            self.assertIsNone(rows[-1][2])  # the last turn has no next observation
            self.assertEqual(rows[0][3], {"ok": False, "code": "BUDGET_EXCEEDED"})
            model = ConsequenceModel.fit_from_log(mind, min_support=2)
            self.assertGreater(model.predict(_obs(1), _act("REPAIR", "e.relay"))["rejected_p"], 0.6)
            self.assertLess(model.predict(_obs(4), _act("REPAIR", "e.relay"))["rejected_p"], 0.4)

    def test_an_empty_or_missing_log_fits_an_empty_model(self):
        with tempfile.TemporaryDirectory() as d:
            model = ConsequenceModel.fit_from_log(Path(d))
            self.assertEqual(model.key_count, 0)
            self.assertEqual(model.predict(_obs(5), _act("WAIT"))["label"], NOT_COMPUTABLE)


if __name__ == "__main__":
    unittest.main()
