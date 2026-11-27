"""D-078: opt-in Controller-local transition log (observation, action, next observation)."""

import gzip
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from noema_orin.transitions import TransitionLog, iter_transitions

try:
    import noema_client  # noqa: F401

    _HAS_CLIENT = True
except ImportError:
    _HAS_CLIENT = False


def _obs(seq, room="room.a", consequence=None, **extra):
    return {"sequence": seq, "cycle": 1, "self": "player.x", "location": {"room_id": room},
            "resources": {"energy": 5}, "last_consequence": consequence, **extra}


def _prop(action, target=None, **arguments):
    return SimpleNamespace(action=action, target_id=target, arguments=arguments or None)


class TransitionLogTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.mind = Path(self._tmp.name) / "mind"
        self.mind.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_disabled_by_default_and_enabled_only_by_explicit_flag(self):
        self.assertIsNone(TransitionLog.from_env(self.mind, env={}))
        self.assertIsNone(TransitionLog.from_env(self.mind, env={"NOEMA_TRANSITION_LOG": "0"}))
        log = TransitionLog.from_env(self.mind, env={"NOEMA_TRANSITION_LOG": "1", "NOEMA_TRANSITION_LOG_MAX_MB": "2",
                                                     "NOEMA_TRANSITION_LOG_KEEP": "3"})
        self.assertIsInstance(log, TransitionLog)
        self.assertEqual(log.max_bytes, 2 * 1024 * 1024)
        self.assertEqual(log.keep, 3)

    def test_append_writes_full_observation_and_final_action(self):
        log = TransitionLog(self.mind)
        log.new_session()
        log.append(canonical=_obs(10), proposal=_prop("MOVE", "north"), source="planner")
        rows = [json.loads(line) for line in (self.mind / "transitions.jsonl").read_text().splitlines()]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["v"], 1)
        self.assertEqual(row["label"], "TELEMETRY")
        self.assertEqual(row["turn"], 0)
        self.assertEqual(row["seq"], 10)
        self.assertEqual(row["source"], "planner")
        self.assertEqual(row["obs"]["location"]["room_id"], "room.a")
        self.assertEqual(row["action"], {"action": "MOVE", "target_id": "north", "arguments": {}})

    def test_iter_transitions_pairs_consecutive_turns_within_a_session_only(self):
        log = TransitionLog(self.mind)
        log.new_session()
        log.append(canonical=_obs(1), proposal=_prop("LOOK"), source="model")
        log.append(canonical=_obs(2, consequence="You look around."), proposal=_prop("MOVE", "north"), source="planner")
        log.append(canonical=_obs(3, room="room.b", consequence="You move north."), proposal=_prop("WAIT"), source="planner")
        log.new_session()  # a new session must not be stitched onto the previous one
        log.append(canonical=_obs(40), proposal=_prop("LOOK"), source="model")
        log.append(canonical=_obs(41, consequence="You look around."), proposal=_prop("WAIT"), source="planner")
        triples = list(iter_transitions(self.mind))
        self.assertEqual([(o["sequence"], a["action"], n["sequence"]) for o, a, n in triples],
                         [(1, "LOOK", 2), (2, "MOVE", 3), (40, "LOOK", 41)])
        self.assertEqual(triples[1][2]["last_consequence"], "You move north.")
        self.assertEqual(triples[1][2]["location"]["room_id"], "room.b")

    def test_secret_shaped_keys_are_dropped_at_any_depth(self):
        log = TransitionLog(self.mind)
        log.new_session()
        canonical = _obs(5, access_token="t0k", nested={"Authorization": "Bearer x", "keep": 1,
                                                        "items": [{"api_key": "k", "name": "wrench"}]},
                         system_prompt="private brief")
        log.append(canonical=canonical, proposal=_prop("LOOK", password="p", track="repair"), source="model")
        text = (self.mind / "transitions.jsonl").read_text()
        for leaked in ("t0k", "Bearer x", "private brief", '"k"', '"p"'):
            self.assertNotIn(leaked, text)
        row = json.loads(text)
        self.assertEqual(row["obs"]["nested"]["keep"], 1)
        self.assertEqual(row["obs"]["nested"]["items"], [{"name": "wrench"}])
        self.assertEqual(row["action"]["arguments"], {"track": "repair"})
        self.assertIn("access_token", canonical)  # the caller's observation is not mutated

    def test_rotation_compresses_segments_and_prunes_the_oldest(self):
        log = TransitionLog(self.mind, max_bytes=600, keep=2)
        log.new_session()
        for seq in range(40):
            log.append(canonical=_obs(seq, filler="x" * 100), proposal=_prop("WAIT"), source="planner")
        segments = sorted(self.mind.glob("transitions-*.jsonl.gz"))
        self.assertEqual(len(segments), 2)
        live = self.mind / "transitions.jsonl"  # absent right after a rotation
        self.assertLess(live.stat().st_size if live.exists() else 0, 600)
        with gzip.open(segments[-1], "rt", encoding="utf-8") as fh:
            self.assertEqual(json.loads(fh.readline())["v"], 1)
        # Reading spans the retained segments and the live file, in order, with no gap inside what was kept.
        seqs = [o["sequence"] for o, _a, _n in iter_transitions(self.mind)]
        self.assertEqual(seqs, list(range(seqs[0], 39)))
        self.assertGreater(seqs[0], 0)  # the oldest segments were pruned

    def test_reopening_continues_segment_numbering(self):
        first = TransitionLog(self.mind, max_bytes=300, keep=100)
        first.new_session()
        for seq in range(10):
            first.append(canonical=_obs(seq, filler="x" * 100), proposal=_prop("WAIT"), source="planner")
        before = {p.name for p in self.mind.glob("transitions-*.jsonl.gz")}
        second = TransitionLog(self.mind, max_bytes=300, keep=100)
        second.new_session()
        for seq in range(10, 20):
            second.append(canonical=_obs(seq, filler="x" * 100), proposal=_prop("WAIT"), source="planner")
        after = {p.name for p in self.mind.glob("transitions-*.jsonl.gz")}
        self.assertTrue(before < after)  # nothing overwritten

    @unittest.skipUnless(os.name == "posix", "POSIX file modes")
    def test_files_are_private(self):
        log = TransitionLog(self.mind, max_bytes=300, keep=5)
        log.new_session()
        for seq in range(10):
            log.append(canonical=_obs(seq, filler="x" * 100), proposal=_prop("WAIT"), source="planner")
        for path in [self.mind / "transitions.jsonl", *self.mind.glob("transitions-*.jsonl.gz")]:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600, path.name)

    def test_private_filename_is_on_the_voice_leak_list(self):
        from noema_orin.voice import _PRIVATE_LEAK_TOKENS

        self.assertIn("transitions.jsonl", _PRIVATE_LEAK_TOKENS)


@unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
class DecideHookTests(unittest.TestCase):
    def _adapter(self):
        from noema_orin.orin_adapter import OrinAdapter

        ad = OrinAdapter(base_url="http://127.0.0.1:9/v1", model="m", brief="b")
        ad.allowed = frozenset({"LOOK", "WAIT", "MOVE", "RECHARGE"})
        ad.verbs = {"RECHARGE"}
        return ad

    def _canon(self, seq):
        return {"sequence": seq, "location": {"room_id": "room.dry", "name": "Dry", "exits": [], "entities": []},
                "resources": {"energy": 0, "storage": 16, "compute": 5},
                "affordances": [{"action": "RECHARGE", "operation": "RECHARGE", "available": True}]}

    def test_decide_logs_the_returned_proposal_and_stays_silent_without_a_log(self):
        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            ad = self._adapter()
            ad.decide({"canonical": self._canon(10)})  # no transition_log attached: nothing written
            self.assertEqual(list(mind.iterdir()), [])
            ad.transition_log = TransitionLog(mind)
            ad.transition_log.new_session()
            first = ad.decide({"canonical": self._canon(11)})
            ad.decide({"canonical": self._canon(12)})
            triples = list(iter_transitions(mind))
            self.assertEqual(len(triples), 1)
            obs, action, nxt = triples[0]
            self.assertEqual((obs["sequence"], nxt["sequence"]), (11, 12))
            self.assertEqual(action["action"], first.action)
            self.assertEqual(obs["affordances"][0]["action"], "RECHARGE")

    def test_a_failing_log_never_stalls_a_turn(self):
        class Broken:
            def append(self, **_kw):
                raise OSError("disk full")

        ad = self._adapter()
        ad.transition_log = Broken()
        self.assertEqual(ad.decide({"canonical": self._canon(10)}).action, "WAIT")


if __name__ == "__main__":
    unittest.main()
