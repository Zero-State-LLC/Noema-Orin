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

    def test_session_split_across_collect_runs_counts_every_turn(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "logs").mkdir()
            log = root / "logs" / "noema-player@m01.log"
            head = [{"member": "m01", "role": "founder", "persona_version": 1}] + [
                {"turn": i, "source": "model", "action": "LOOK"} for i in range(5)]
            log.write_text("\n".join(json.dumps(x) for x in head) + "\n")
            db = open_db(root)
            self.assertEqual(collect(root, db), 0)  # session still running
            tail = [{"turn": i, "source": "model", "action": "ORG_OFFICE_ASSIGN"} for i in range(5, 8)] + [
                {"member": "m01", "role": "founder", "actions": 8, "stop_reason": "duration_elapsed"}]
            with log.open("a") as f:
                f.write("\n".join(json.dumps(x) for x in tail) + "\n")
            self.assertEqual(collect(root, db), 1)
            out = digest(db)["members"]["m01"]
            self.assertEqual((out["turns"], out["role"]), (8, "founder"))
            db.close()

    def test_world_incident_alert_tracks_latest_session_only(self):
        def write(root, member, reasons):
            rows = []
            for r in reasons:
                rows += [{"member": member, "role": "custodian", "persona_version": 1},
                         {"turn": 1, "source": "model", "action": "MOVE"},
                         {"member": member, "role": "custodian", "actions": 1, "stop_reason": r}]
            (root / "logs" / f"noema-player@{member}.log").write_text("\n".join(json.dumps(x) for x in rows) + "\n")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "logs").mkdir()
            write(root, "m01", ["duration_elapsed", "world_incident"])
            write(root, "m02", ["world_incident", "duration_elapsed"])
            db = open_db(root)
            collect(root, db)
            alerts = digest(db)["alerts"]
            self.assertTrue(alerts[0].startswith("world INCIDENT"), alerts)
            self.assertIn("(m01)", alerts[0])
            db.close()

    def test_zero_energy_streak_alert(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "logs").mkdir()
            rows = [{"turn": 1, "action": "MOVE", "budgets": {"energy": 3}}] + [
                {"turn": i, "action": "WAIT", "budgets": {"energy": 0}} for i in range(2, 14)]
            (root / "logs" / "noema-player@m03.log").write_text("\n".join(json.dumps(x) for x in rows) + "\n")
            (root / "logs" / "noema-player@m05.log").write_text(json.dumps(rows[0]) + "\n")
            db = open_db(root)
            collect(root, db)
            self.assertEqual(digest(db)["alerts"], ["m03: energy 0 for last 12 turns (Noema#907)"])
            db.close()

    def test_world_incident_stops_are_not_an_agents_early_end(self):
        """D-095: 133 of m01's 163 sessions in 24h stopped on WORLD_INCIDENT during three world INCIDENTs, and the
        kiosk showed 'm01: 134/163 sessions ended early' for every member, hours after the world recovered. Those
        sessions say nothing about the agent; the world INCIDENT alert already covers the outage while it lasts."""
        def write(root, member, reasons):
            rows = []
            for r in reasons:
                rows += [{"member": member, "role": "custodian", "persona_version": 1},
                         {"turn": 1, "source": "model", "action": "MOVE"},
                         {"member": member, "role": "custodian", "actions": 1, "stop_reason": r}]
            (root / "logs" / f"noema-player@{member}.log").write_text("\n".join(json.dumps(x) for x in rows) + "\n")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "logs").mkdir()
            write(root, "m01", ["world_incident"] * 8 + ["duration_elapsed"] * 2)
            write(root, "m02", ["circuit_breaker"] * 3 + ["world_incident"] * 5 + ["duration_elapsed"] * 2)
            db = open_db(root)
            collect(root, db)
            alerts = digest(db)["alerts"]
            self.assertFalse(any(a.startswith("m01:") and "ended early" in a for a in alerts), alerts)
            self.assertIn("m02: 3/5 sessions ended early", alerts)
            db.close()

    def test_unit_stops_are_not_an_agents_early_end(self):
        """D-099: a restart or stop of the unit now ends its session at a turn boundary with a session line that
        says user_interrupt. Before, it was SIGKILLed and left no line at all, so the new lines must not read as
        the agent cutting its own sessions short after a rolling restart."""
        def write(root, member, reasons):
            rows = []
            for r in reasons:
                rows += [{"member": member, "role": "custodian", "persona_version": 1},
                         {"turn": 1, "source": "model", "action": "MOVE"},
                         {"member": member, "role": "custodian", "actions": 1, "stop_reason": r}]
            (root / "logs" / f"noema-player@{member}.log").write_text("\n".join(json.dumps(x) for x in rows) + "\n")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "logs").mkdir()
            write(root, "m01", ["user_interrupt"] * 6 + ["world_incident"] * 2 + ["duration_elapsed"] * 2)
            write(root, "m02", ["circuit_breaker"] * 3 + ["user_interrupt"] * 5 + ["duration_elapsed"] * 2)
            db = open_db(root)
            collect(root, db)
            out = digest(db)
            alerts = out["alerts"]
            self.assertEqual(out["members"]["m01"]["unit_stop_sessions"], 6)
            self.assertEqual(out["members"]["m01"]["sessions"], 10, "a stopped session is still a session")
            self.assertFalse(any(a.startswith("m01:") and "ended early" in a for a in alerts), alerts)
            self.assertIn("m02: 3/5 sessions ended early", alerts)
            db.close()


if __name__ == "__main__":
    unittest.main()


def _session(member, role, by_verb, turns, no_prediction):
    return {"member": member, "role": role, "actions": turns, "stop_reason": "duration_elapsed",
            "consequence": {"label": "INFERRED", "turns": turns, "no_prediction": no_prediction, "by_verb": by_verb}}


class ConsequenceDigestTests(unittest.TestCase):
    """C4 (#199): shadow accuracy from the C3 session summaries, per member and per verb."""

    def _db(self, root, logs):
        (root / "logs").mkdir()
        for member, rows in logs.items():
            (root / "logs" / f"noema-player@{member}.log").write_text("\n".join(json.dumps(x) for x in rows) + "\n")
        db = open_db(root)
        collect(root, db)
        return db

    def test_digest_reports_precision_recall_and_no_prediction_share_per_member(self):
        with tempfile.TemporaryDirectory() as d:
            repair = {"turns": 10, "predicted": 8, "tp": 3, "fp": 1, "fn": 2, "tn": 2, "right": 5, "wrong": 3, "budget_scored": 7, "budget_mae": 0.4}
            wait = {"turns": 10, "predicted": 6, "tp": 0, "fp": 0, "fn": 0, "tn": 6, "right": 6, "wrong": 0, "budget_scored": 6, "budget_mae": 0.0}
            db = self._db(Path(d), {
                "m03": [{"member": "m03", "role": "custodian", "persona_version": 1},
                        _session("m03", "custodian", {"REPAIR": repair, "WAIT": wait}, 20, 6),
                        _session("m03", "custodian", {"REPAIR": repair}, 10, 2)],
                "m05": [{"member": "m05", "role": "speaker", "persona_version": 1},
                        {"member": "m05", "role": "speaker", "actions": 4, "stop_reason": "duration_elapsed"}],
            })
            members = digest(db)["members"]
            db.close()
        got = members["m03"]["consequence"]
        self.assertEqual(got["label"], "INFERRED")
        self.assertEqual((got["sessions"], got["turns"], got["predictions"]), (2, 30, 22))
        self.assertEqual(got["no_prediction_share"], round(8 / 30, 3))
        self.assertEqual(got["rejection_scored"], 22)
        self.assertEqual(got["rejection_precision"], 0.75)  # tp 6 / (tp 6 + fp 2)
        self.assertEqual(got["rejection_recall"], 0.6)  # tp 6 / (tp 6 + fn 4)
        self.assertEqual(got["by_verb"]["REPAIR"], {"turns": 20, "predicted": 16, "tp": 6, "fp": 2, "fn": 4, "tn": 4})
        self.assertEqual(got["by_verb"]["WAIT"]["tn"], 6)
        self.assertNotIn("consequence", members["m05"])  # shadow off: no data, not zeros

    def test_precision_and_recall_are_not_computable_without_the_cases_they_need(self):
        with tempfile.TemporaryDirectory() as d:
            wait = {"turns": 5, "predicted": 5, "tp": 0, "fp": 0, "fn": 0, "tn": 5}
            db = self._db(Path(d), {"m06": [{"member": "m06", "role": "surveyor", "persona_version": 1},
                                             _session("m06", "surveyor", {"WAIT": wait}, 5, 0)]})
            got = digest(db)["members"]["m06"]["consequence"]
            db.close()
        self.assertEqual(got["rejection_precision"], "NOT_COMPUTABLE")
        self.assertEqual(got["rejection_recall"], "NOT_COMPUTABLE")
        self.assertEqual(got["no_prediction_share"], 0.0)

    def test_collect_is_incremental_and_malformed_summaries_are_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rows = [{"member": "m03", "role": "custodian", "persona_version": 1},
                    {"member": "m03", "role": "custodian", "actions": 1, "stop_reason": "duration_elapsed", "consequence": "NOT_COMPUTABLE"},
                    {"member": "m03", "role": "custodian", "actions": 1, "stop_reason": "duration_elapsed",
                     "consequence": {"turns": "many", "no_prediction": None, "by_verb": {"WAIT": {"turns": 2, "predicted": "x", "tp": True}, "BAD": 7}}},
                    _session("m03", "custodian", {"WAIT": {"turns": 4, "predicted": 4, "tp": 1, "fp": 0, "fn": 0, "tn": 3}}, 4, 0)]
            db = self._db(root, {"m03": rows})
            collect(root, db)  # a second pass must not double count
            got = digest(db)["members"]["m03"]["consequence"]
            db.close()
        self.assertEqual(got["by_verb"]["WAIT"], {"turns": 6, "predicted": 4, "tp": 1, "fp": 0, "fn": 0, "tn": 3})
        self.assertNotIn("BAD", got["by_verb"])

    def test_a_metrics_db_from_before_this_change_still_digests(self):
        with tempfile.TemporaryDirectory() as d:
            db = self._db(Path(d), {"m03": [{"member": "m03", "role": "custodian", "persona_version": 1},
                                             {"member": "m03", "role": "custodian", "actions": 1, "stop_reason": "duration_elapsed"}]})
            db.execute("DROP TABLE consequence")
            members = digest(db)["members"]
            db.close()
        self.assertNotIn("consequence", members["m03"])
