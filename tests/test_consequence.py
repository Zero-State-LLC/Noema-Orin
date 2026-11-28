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


def _result(action, ok=True, code=None):
    return SimpleNamespace(ok=ok, reason=None, failure=None, proposal=SimpleNamespace(action=action),
                           result=SimpleNamespace(ok=ok, error={"code": code} if code else None))


def _trained():
    model = ConsequenceModel(min_support=3)
    for _ in range(6):
        model.observe(_obs(1), _act("REPAIR", "e.relay"), _obs(1), NO)
        model.observe(_obs(5), _act("REPAIR", "e.relay"), _obs(2), OK)
    return model


class ShadowScorerTests(unittest.TestCase):
    """C3 (#198): score predictions against what happened, per session, without changing behaviour."""

    def test_session_summary_counts_predictions_and_rejection_hits_by_verb(self):
        from noema_orin.consequence import ShadowScorer

        model, scorer = _trained(), ShadowScorer()
        plan = [(1, "REPAIR", False), (5, "REPAIR", True), (5, "REPAIR", False), (5, "TRADE", True)]
        for energy, action, _ok in plan:
            scorer.note(_obs(energy), _act(action, "e.relay"), model.predict(_obs(energy), _act(action, "e.relay")))
        summary = scorer.finish([_result(a, ok, None if ok else "X") for _e, a, ok in plan], model)
        self.assertEqual(summary["label"], "INFERRED")
        self.assertEqual(summary["turns"], 4)
        self.assertEqual(summary["no_prediction"], 1)  # TRADE was never seen
        repair = summary["by_verb"]["REPAIR"]
        self.assertEqual((repair["turns"], repair["predicted"]), (3, 3))
        # predicted reject+was rejected, predicted ok+was ok, predicted ok+was rejected
        self.assertEqual((repair["tp"], repair["tn"], repair["fn"], repair["fp"]), (1, 1, 1, 0))
        self.assertEqual((repair["right"], repair["wrong"]), (2, 1))
        self.assertEqual(summary["by_verb"]["TRADE"]["predicted"], 0)

    def test_budget_error_is_scored_against_the_next_observation_of_the_session(self):
        from noema_orin.consequence import ShadowScorer

        model, scorer = _trained(), ShadowScorer()
        # Model expects REPAIR at energy 5 to cost 3. First turn really costs 3, second really costs 5.
        for energy in (9, 6, 1):
            obs = _obs(energy)
            obs["resources"]["energy"] = energy
            scorer.note(obs, _act("REPAIR", "e.relay"), model.predict(_obs(5), _act("REPAIR", "e.relay")))
        summary = scorer.finish([_result("REPAIR")] * 3, model)
        repair = summary["by_verb"]["REPAIR"]
        self.assertEqual(repair["budget_scored"], 2)  # the last turn has no next observation
        self.assertAlmostEqual(repair["budget_mae"], ((0 + 2) / 2) / 5, places=4)  # averaged over the five budgets

    def test_finish_folds_the_session_into_the_model_like_a_fit_from_the_log(self):
        from noema_orin.consequence import ShadowScorer

        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            log, scorer, live = TransitionLog(mind), ShadowScorer(), ConsequenceModel(min_support=2)
            log.new_session()
            turns = []
            for i in range(12):
                energy, ok = i % 6, i % 6 >= 3
                proposal = SimpleNamespace(action="REPAIR", target_id="e.relay", arguments=None)
                log.append(canonical=_obs(energy), proposal=proposal, source="planner")
                scorer.note(_obs(energy), proposal, live.predict(_obs(energy), proposal))
                turns.append(_result("REPAIR", ok, None if ok else "BUDGET_EXCEEDED"))
            log.record_outcomes(turns)
            scorer.finish(turns, live)
            refit = ConsequenceModel.fit_from_log(mind, min_support=2)
            for energy in range(8):
                self.assertEqual(live.predict(_obs(energy), _act("REPAIR", "e.relay")),
                                 refit.predict(_obs(energy), _act("REPAIR", "e.relay")), energy)

    def test_a_session_without_a_report_still_teaches_budgets_and_then_resets(self):
        from noema_orin.consequence import ShadowScorer

        model, scorer = ConsequenceModel(min_support=2), ShadowScorer()
        for energy in (5, 7, 9, 11):
            scorer.note(_obs(energy), _act("WAIT"), model.predict(_obs(energy), _act("WAIT")))
        self.assertIsNone(scorer.finish(None, model))  # transport drop: nothing to score
        got = model.predict(_obs(7), _act("WAIT"))
        self.assertEqual(got["budget_delta"]["energy"], 2)
        self.assertEqual(got["rejected_p"], NOT_COMPUTABLE)
        self.assertIsNone(scorer.finish([], model))  # already reset: nothing left over


class AttachShadowTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.mind = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _adapter(self, with_log=True):
        return SimpleNamespace(transition_log=TransitionLog(self.mind) if with_log else None,
                               consequence_model=None, consequence_scorer=None)

    def test_off_unless_both_the_transition_log_and_the_shadow_flag_are_on(self):
        from noema_orin.consequence import attach_shadow

        for adapter, env in ((self._adapter(), {}), (self._adapter(), {"NOEMA_CONSEQUENCE_SHADOW": "0"}),
                             (self._adapter(with_log=False), {"NOEMA_CONSEQUENCE_SHADOW": "1"})):
            self.assertFalse(attach_shadow(adapter, self.mind, env=env))
            self.assertIsNone(adapter.consequence_model)
            self.assertIsNone(adapter.consequence_scorer)
        adapter = self._adapter()
        self.assertTrue(attach_shadow(adapter, self.mind, env={"NOEMA_CONSEQUENCE_SHADOW": "1"}))
        self.assertIsNotNone(adapter.consequence_model)
        self.assertIsNotNone(adapter.consequence_scorer)

    def test_attaching_fits_from_rows_already_in_the_log(self):
        from noema_orin.consequence import attach_shadow

        adapter = self._adapter()
        adapter.transition_log.new_session()
        for _ in range(8):
            adapter.transition_log.append(canonical=_obs(5), proposal=SimpleNamespace(action="WAIT", target_id=None, arguments=None),
                                          source="planner")
        attach_shadow(adapter, self.mind, env={"NOEMA_CONSEQUENCE_SHADOW": "1"})
        self.assertEqual(adapter.consequence_model.predict(_obs(5), _act("WAIT"))["label"], "INFERRED")

    def test_closing_a_session_never_raises(self):
        from noema_orin.consequence import close_shadow_session

        class Broken:
            def finish(self, *_a):
                raise RuntimeError("boom")

            def reset(self):
                pass

        self.assertIsNone(close_shadow_session(SimpleNamespace(consequence_model=None, consequence_scorer=None), []))
        self.assertIsNone(close_shadow_session(SimpleNamespace(consequence_model=ConsequenceModel(), consequence_scorer=Broken()), []))

    def test_only_the_newest_segments_are_read_when_asked(self):
        log = TransitionLog(self.mind, max_bytes=300, keep=100)
        log.new_session()
        for seq in range(10):
            log.append(canonical={"sequence": seq, "filler": "x" * 200}, proposal=SimpleNamespace(action="WAIT", target_id=None, arguments=None),
                       source="planner")
        self.assertEqual(len(list(iter_labelled(self.mind))), 10)
        self.assertEqual([o["sequence"] for o, _a, _n, _o in iter_labelled(self.mind, newest_segments=3)], [7, 8, 9])


try:
    import noema_client  # noqa: F401

    _HAS_CLIENT = True
except ImportError:
    _HAS_CLIENT = False


@unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
class DecideShadowTests(unittest.TestCase):
    def _adapter(self):
        from noema_orin.orin_adapter import OrinAdapter

        ad = OrinAdapter(base_url="http://127.0.0.1:9/v1", model="m", brief="b")
        ad.allowed = frozenset({"LOOK", "WAIT", "MOVE", "RECHARGE"})
        ad.verbs = {"RECHARGE"}
        return ad

    def _sequence(self):
        return [{"sequence": 10 + i, "location": {"room_id": "room.dry", "name": "Dry", "exits": [], "entities": []},
                 # Energy 0 keeps every turn on the scripted planner path: no model call, no network.
                 "resources": {"energy": 0, "storage": 16, "compute": 5},
                 "affordances": [{"action": "RECHARGE", "operation": "RECHARGE", "available": True},
                                 {"action": "LOOK", "available": True}, {"action": "WAIT", "available": True}]}
                for i in range(8)]

    def _run(self, adapter):
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            proposals = [adapter.decide({"canonical": c}) for c in self._sequence()]
        return [(p.action, p.target_id, dict(p.arguments or {})) for p in proposals], out.getvalue().splitlines()

    def test_decide_returns_identical_proposals_with_the_model_attached_and_detached(self):
        from noema_orin.consequence import ShadowScorer

        plain, plain_lines = self._run(self._adapter())
        shadowed = self._adapter()
        shadowed.consequence_model, shadowed.consequence_scorer = ConsequenceModel(min_support=1), ShadowScorer()
        for c in self._sequence():
            shadowed.consequence_model.observe(c, _act("WAIT"), c, OK)
        got, lines = self._run(shadowed)
        self.assertEqual(got, plain)
        import json

        self.assertTrue(all("consequence" not in json.loads(line) for line in plain_lines))
        turn_lines = [json.loads(line) for line in lines if '"turn"' in line]
        self.assertEqual(len(turn_lines), 8)
        self.assertTrue(all("consequence" in line for line in turn_lines))
        self.assertTrue(any(isinstance(line["consequence"], dict) and line["consequence"]["label"] == "INFERRED" for line in turn_lines))

    def test_an_unseen_command_is_reported_as_not_computable(self):
        from noema_orin.consequence import ShadowScorer

        import json

        adapter = self._adapter()
        adapter.consequence_model, adapter.consequence_scorer = ConsequenceModel(), ShadowScorer()
        _got, lines = self._run(adapter)
        self.assertEqual({json.loads(line)["consequence"] for line in lines if '"turn"' in line}, {NOT_COMPUTABLE})

    def test_a_failing_model_never_stalls_a_turn(self):
        class Broken:
            def predict(self, *_a):
                raise RuntimeError("boom")

        plain, _ = self._run(self._adapter())
        adapter = self._adapter()
        adapter.consequence_model = Broken()
        got, lines = self._run(adapter)
        self.assertEqual(got, plain)
        self.assertTrue(any("consequence_error" in line for line in lines))


if __name__ == "__main__":
    unittest.main()


def _outage(action, code="WORLD_INCIDENT", failure="WORLD_INCIDENT"):
    return SimpleNamespace(ok=False, reason=None, failure=SimpleNamespace(value=failure), proposal=SimpleNamespace(action=action),
                           result=SimpleNamespace(ok=False, error={"code": code}))


class WorldLevelFailureTests(unittest.TestCase):
    """A turn that failed because the world or the connection was unavailable says nothing about the action."""

    def _predictions(self, model):
        return [model.predict(_obs(e), _act("REPAIR", "e.relay")) for e in range(8)]

    def test_outage_failures_are_not_learned_as_rejections_or_as_zero_cost(self):
        baseline, model = _trained(), _trained()
        for _ in range(50):
            model.observe(_obs(5), _act("REPAIR", "e.relay"), _obs(5), {"ok": False, "code": "WORLD_INCIDENT", "failure": "WORLD_INCIDENT"})
            model.observe(_obs(5), _act("REPAIR", "e.relay"), _obs(5), {"ok": False, "code": "STALE_HEAD", "failure": "ACTION_REJECTED"})
            model.observe(_obs(5), _act("REPAIR", "e.relay"), _obs(5), {"ok": False, "code": "RETRYABLE_TRANSPORT", "failure": "RETRYABLE_TRANSPORT"})
        self.assertEqual(self._predictions(model), self._predictions(baseline))

    def test_a_rejection_of_the_action_itself_still_counts(self):
        model = ConsequenceModel(min_support=3)
        for _ in range(6):
            model.observe(_obs(1), _act("REPAIR", "e.relay"), _obs(1), {"ok": False, "code": "BUDGET_EXCEEDED", "failure": "ACTION_REJECTED"})
        self.assertGreater(model.predict(_obs(1), _act("REPAIR", "e.relay"))["rejected_p"], 0.8)

    def test_outage_rows_already_in_the_log_are_skipped_on_refit(self):
        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            log = TransitionLog(mind)
            proposal = SimpleNamespace(action="REPAIR", target_id="e.relay", arguments=None)
            log.new_session()
            for _ in range(6):
                log.append(canonical=_obs(5), proposal=proposal, source="planner")
            log.record_outcomes([_result("REPAIR")] * 6)
            clean = self._predictions(ConsequenceModel.fit_from_log(mind, min_support=3))
            log.new_session()
            for _ in range(40):
                log.append(canonical=_obs(5), proposal=proposal, source="planner")
            log.record_outcomes([_outage("REPAIR")] * 40)
            self.assertEqual(self._predictions(ConsequenceModel.fit_from_log(mind, min_support=3)), clean)
            self.assertLess(clean[5]["rejected_p"], 0.5)

    def test_the_scorer_neither_scores_nor_folds_outage_turns_and_counts_them(self):
        from noema_orin.consequence import ShadowScorer

        baseline, model, scorer = _trained(), _trained(), ShadowScorer()
        for _ in range(10):
            scorer.note(_obs(5), _act("REPAIR", "e.relay"), model.predict(_obs(5), _act("REPAIR", "e.relay")))
        report = [_result("REPAIR")] + [_outage("REPAIR", "STALE_HEAD", "ACTION_REJECTED")] + [_outage("REPAIR")] * 8
        summary = scorer.finish(report, model)
        repair = summary["by_verb"]["REPAIR"]
        self.assertEqual(summary["excluded"], 9)
        self.assertEqual((repair["tp"], repair["fp"], repair["fn"], repair["tn"]), (0, 0, 0, 1))
        self.assertEqual(repair["budget_scored"], 1)  # only the accepted turn; outage turns are not scored
        self.assertLessEqual(model.predict(_obs(5), _act("REPAIR", "e.relay"))["rejected_p"],
                             baseline.predict(_obs(5), _act("REPAIR", "e.relay"))["rejected_p"])

    def test_live_fold_and_refit_still_agree_across_an_outage(self):
        from noema_orin.consequence import ShadowScorer

        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            log, scorer, live = TransitionLog(mind), ShadowScorer(), ConsequenceModel(min_support=2)
            log.new_session()
            proposal = SimpleNamespace(action="REPAIR", target_id="e.relay", arguments=None)
            turns = []
            for i in range(12):
                energy = i % 6
                log.append(canonical=_obs(energy), proposal=proposal, source="planner")
                scorer.note(_obs(energy), proposal, live.predict(_obs(energy), proposal))
                turns.append(_outage("REPAIR") if i % 4 == 3 else _result("REPAIR", energy >= 3, None if energy >= 3 else "BUDGET_EXCEEDED"))
            log.record_outcomes(turns)
            scorer.finish(turns, live)
            refit = ConsequenceModel.fit_from_log(mind, min_support=2)
            for energy in range(8):
                self.assertEqual(live.predict(_obs(energy), _act("REPAIR", "e.relay")),
                                 refit.predict(_obs(energy), _act("REPAIR", "e.relay")), energy)
