import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from noema_orin.health import RoleHealthTracker
from noema_orin.memory import Memory, WorldMap
from noema_orin.metrics import collect, digest, open_db
from noema_orin.orin_adapter import OrinAdapter, _options
from noema_orin.persona import (
    MAX_SEED_DISTANCE,
    SEEDS,
    apply_reflection,
    load_or_seed,
    mean_revert_toward_seed,
    rollback_to_version,
)
from noema_orin.planner import facts_from, route
from noema_orin.roles import DENY_ALWAYS, role_for
from noema_orin.rsi import (
    RsiRatchet,
    apply_knob_deltas,
    build_session_dossier,
    compute_fitness,
    load_agenda,
    load_or_init_knobs,
    replay_verify,
    save_agenda,
)

HAS_CLIENT = importlib.util.find_spec("noema_client") is not None


class HardenedRsiTests(unittest.TestCase):
    def test_seed_tether_prevents_trait_saturation_and_rollback_restores(self):
        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            p = load_or_seed(mind, "surveyor")
            seed_caution = SEEDS["surveyor"]["traits"]["caution"]
            for _ in range(10):
                p, ok = apply_reflection(mind, p, {"trait_deltas": {"caution": 0.1}})
                self.assertTrue(ok)
            self.assertLessEqual(p["traits"]["caution"], round(seed_caution + MAX_SEED_DISTANCE, 3))
            reverted = mean_revert_toward_seed(p, step=0.05)
            self.assertLess(reverted["traits"]["caution"], p["traits"]["caution"])
            restored = rollback_to_version(mind, 1)
            self.assertEqual(restored["version"], 1)
            self.assertEqual(restored["traits"]["caution"], seed_caution)

    def test_grounded_lesson_validation_and_deduplication(self):
        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            p = load_or_seed(mind, "archivist")
            # Ungrounded sequence is dropped while valid trait delta succeeds
            p2, ok = apply_reflection(
                mind, p, {"trait_deltas": {"curiosity": 0.05}, "lesson": "Fabricated scar.", "lesson_seq": 999},
                valid_sequences={100, 101},
            )
            self.assertTrue(ok)
            self.assertEqual(p2["lessons"], [])
            # Grounded lesson is accepted with seq tag, and near-duplicate is deduplicated
            p3, ok = apply_reflection(
                mind, p2, {"lesson": "Relay Quarter holds active economic scar", "lesson_seq": 101},
                valid_sequences={100, 101},
            )
            self.assertTrue(ok)
            self.assertEqual(len(p3["lessons"]), 1)
            self.assertIn("[seq 101]", p3["lessons"][0])
            p4, ok = apply_reflection(
                mind, p3, {"lesson": "Relay Quarter holds active economic scar now", "lesson_seq": 101},
                valid_sequences={100, 101},
            )
            self.assertTrue(ok)
            self.assertEqual(len(p4["lessons"]), 1)

    def test_policy_knobs_bounded_and_unknown_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            knobs = load_or_init_knobs(mind, SEEDS["quartermaster"]["traits"])
            nxt, ok = apply_knob_deltas(knobs, {"scar_avoidance_weight": 0.5, "dwell_before_route": 10})
            self.assertTrue(ok)
            self.assertLessEqual(nxt["scar_avoidance_weight"], 1.0)
            self.assertLessEqual(nxt["dwell_before_route"], 4)
            bad, ok2 = apply_knob_deltas(knobs, {"allow_trade": 1})
            self.assertFalse(ok2)
            self.assertEqual(bad, knobs)

    def test_rsi_ratchet_auto_rollbacks_and_quarantines_regression(self):
        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            p1 = load_or_seed(mind, "custodian")
            knobs = load_or_init_knobs(mind, p1["traits"])
            ratchet = RsiRatchet(mind)
            good_dossier = build_session_dossier(
                role="custodian",
                role_verbs=set(role_for("custodian")["verbs"]),
                turn_log=[{"seq": i, "room": "r1", "action": "REPAIR", "budgets": {"energy": 5}} for i in range(1, 11)],
            )
            self.assertGreater(compute_fitness(good_dossier), 0.7)
            v0 = ratchet.evaluate_session(good_dossier, p1, knobs)
            self.assertEqual(v0["verdict"], "BASELINE")
            patch = {"trait_deltas": {"caution": 0.1}, "knob_deltas": {"dwell_before_route": 1}}
            ok, sig = ratchet.register_candidate(patch, persona_version=2)
            self.assertTrue(ok)
            self.assertFalse(ratchet.can_propose())
            # Regression via high rejection rate triggers immediate rollback + quarantine
            bad_dossier = build_session_dossier(
                role="custodian",
                role_verbs=set(role_for("custodian")["verbs"]),
                turn_log=[{"seq": i, "room": "r1", "action": "WAIT", "budgets": {"energy": 2}} for i in range(11, 21)],
                rejections={"by_verb_code": {"REPAIR:DENIED": 5}},
            )
            v1 = ratchet.evaluate_session(bad_dossier, {**p1, "version": 2}, {**knobs, "dwell_before_route": 3})
            self.assertEqual(v1["verdict"], "ROLLED_BACK")
            self.assertEqual(v1["rollback_persona_version"], 1)
            self.assertIn(sig, ratchet.quarantined_signatures())
            # Re-proposing quarantined mutation is refused
            ok2, why = ratchet.register_candidate(patch, persona_version=3)
            self.assertFalse(ok2)
            self.assertEqual(why, "quarantined")

    def test_world_failures_do_not_count_as_rejections(self):
        """D-086: an INCIDENT or a settlement race is the world's failure, not the persona's (cf. D-083).

        The ratchet hard-fails a candidate above a 15% rejection rate, so counting WORLD_INCIDENT and
        STALE_HEAD would quarantine a mutation for an outage it did not cause.
        """
        turn_log = [{"seq": i, "room": "r1", "action": "REPAIR", "budgets": {"energy": 5}} for i in range(1, 11)]
        dossier = build_session_dossier(
            role="custodian",
            role_verbs=set(role_for("custodian")["verbs"]),
            turn_log=turn_log,
            rejections={"by_verb_code": {"REPAIR:WORLD_INCIDENT": 6, "MOVE:STALE_HEAD": 2, "REPAIR:NOT_FOUND": 1}},
        )
        self.assertEqual(dossier["rejection_count"], 1)
        self.assertEqual(dossier["rejection_rate"], 0.1)
        self.assertEqual(dossier["world_failure_count"], 8)
        self.assertEqual(dossier["rejections_by_code"]["REPAIR:WORLD_INCIDENT"], 6)

    def test_persistent_agenda_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            mind = Path(d)
            save_agenda(mind, {"held_track": "surveyor", "build_room": "room.forge", "epoch": 3, "steps": ["map"], "updated_seq": 42})
            loaded = load_agenda(mind)
            self.assertEqual(loaded["held_track"], "surveyor")
            self.assertEqual(loaded["build_room"], "room.forge")
            self.assertEqual(loaded["updated_seq"], 42)

    def test_health_tracker_separates_planner_from_workers_ai_calls(self):
        tracker = RoleHealthTracker(role="Tallow-Quartermaster")
        tracker.record_turn(verb="SUPPLY", used_workers_ai=False, used_planner=True, source_sequence=1)
        tracker.record_turn(verb="HARVEST", used_workers_ai=True, used_planner=False, source_sequence=2)
        summary = tracker.summary()
        self.assertEqual(summary["planner_turns"], 1)
        self.assertEqual(summary["workers_ai_calls"], 1)
        self.assertEqual(summary["ollama_fallbacks"], 0)

    def test_metrics_surfaces_rsi_rollback_alert(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "logs").mkdir()
            rows = [
                {"member": "m03", "role": "custodian", "persona_version": 2},
                {"turn": 1, "source": "planner", "action": "REPAIR"},
                {"member": "m03", "role": "custodian", "actions": 1, "stop_reason": "duration_elapsed",
                 "rsi": {"verdict": "ROLLED_BACK", "fitness": 0.2, "reason": "fitness_regression"}},
            ]
            (root / "logs" / "noema-player@m03.log").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            db = open_db(root)
            collect(root, db)
            alerts = digest(db)["alerts"]
            self.assertTrue(any("rsi_rollback" in a for a in alerts))
            db.close()


class DeepTimeIntegrationTests(unittest.TestCase):
    def test_world_map_records_scars_lore_pressure_and_fallow_routes(self):
        with tempfile.TemporaryDirectory() as d:
            wm = WorldMap(Path(d))
            wm.observe("room.a", "Room A", 10, ["room.b", "room.c"], ["HARVEST", "MOVE"])
            wm.observe("room.b", "Room B", 11, ["room.a"], ["HARVEST", "MOVE"])
            wm.observe("room.c", "Room C", 12, ["room.a"], ["HARVEST", "MOVE"])
            wm.observe_deep_time("room.b", {
                "sequence": 11,
                "scars": [{"scar_id": "scar.1", "domain": "economic", "strength": 0.6, "reconstruction_confidence": 0.2}],
                "active_norms": {"harvest_pressure": 4},
                "lore_attractors": [{"attractor_id": "lore.1", "label": "overharvest", "weight": 0.5, "basin": "forming"}],
                "culture_lines": ["This site has a maintenance tradition."],
            })
            wm.observe_deep_time("room.c", {"sequence": 12, "scars": [], "active_norms": {"harvest_pressure": 0}})
            self.assertEqual(wm.scarred_rooms(near="room.a"), ["room.b"])
            self.assertEqual(wm.room_pressure_for("room.b"), 4.0)
            canon = {
                "location": {
                    "room_id": "room.a", "name": "Room A",
                    "exits": [{"direction": "east", "to_room_id": "room.b"}, {"direction": "west", "to_room_id": "room.c"}],
                }
            }
            # Fallow routing avoids scarred high-pressure room.b and heads west to room.c
            self.assertEqual(route(canon, wm, {"HARVEST"}, explorer=False, avoid_pressure=True), "west")
            # Archivist scar-seeking heads east to scarred room.b
            self.assertEqual(route(canon, wm, {"RECONSTRUCT"}, explorer=False, seek_scars=True), "east")

    def test_facts_from_captures_deep_time_and_culture(self):
        canon = {
            "location": {"room_id": "room.x", "name": "Relay Quarter"},
            "scars": [{"scar_id": "s1", "domain": "economic", "strength": 0.4}],
            "lore_attractors": [{"attractor_id": "l1", "label": "surge", "basin": "crystallized"}],
            "culture_lines": ["This site has a maintenance tradition."],
            "inherited_lines": ["You inherit a record of an economic scar."],
            "rumor_lines": ["You heard a report from Cantor-Speaker."],
            "active_norms": {"harvest_pressure": 3},
        }
        kinds = {k for k, _ in facts_from(canon)}
        self.assertEqual(kinds, {"scar", "lore", "culture", "inherited", "rumor", "pressure"})

    @unittest.skipUnless(HAS_CLIENT, "needs noema-client")
    def test_multi_controller_attest_coalition_and_replay_gate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wm = WorldMap(root)
            mem = Memory(root / "mind")
            spec = role_for("surveyor")

            def make_adapter():
                a = OrinAdapter(base_url="http://127.0.0.1:9/v1", model="m", brief="b")
                a.allowed = frozenset(spec["allow"])
                a.verbs = set(spec["verbs"])
                a.memory = mem
                a.world_map = wm
                a.explorer = True
                return a

            scarred_snap = {
                "self": "player.Perigee-Surveyor",
                "sequence": 50,
                "location": {
                    "room_id": "room.relay-quarter",
                    "name": "Relay Quarter",
                    "exits": [{"direction": "west", "to_room_id": "room.civic-exchange"}],
                },
                "resources": {"energy": 5, "attention": 6, "storage": 16},
                "scars": [{"scar_id": "scar.1", "domain": "economic", "strength": 0.45}],
                "players_here": [{"player_id": "player.Rivet-Custodian", "handle": "Rivet-Custodian"}],
                "last_consequence": "Rivet-Custodian repaired relay-7.",
                "affordances": [
                    {"action": "ATTEST", "operation": "ATTEST", "target_id": "entity.relay-7", "available": True},
                    {"action": "MOVE", "operation": "MOVE", "target_id": "west", "available": True},
                ],
            }
            adapter = make_adapter()
            prop = adapter.decide({"canonical": scarred_snap})
            self.assertEqual(prop.action, "ATTEST")
            self.assertEqual(mem.relations("player.Rivet-Custodian")["supporting"], 1)
            gate = replay_verify(make_adapter, [scarred_snap], denied_verbs=set(DENY_ALWAYS))
            self.assertTrue(gate["ok"])
            self.assertEqual(gate["actions"], ["ATTEST"])


if __name__ == "__main__":
    unittest.main()
