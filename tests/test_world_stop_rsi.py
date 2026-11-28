"""D-101: the session-opening ENTER_WORLD keeps its code, and a session the world ended gives the ratchet no sample.

Live (2026-11-28): 681 session lines carried "?:ACTION_REJECTED"; 678 also carried a WORLD_INCIDENT refusal. It was
the ENTER_WORLD that opens each session, refused during an INCIDENT. noema-client's play() keeps that result as
the bare CommandResult from act(), which has no `proposal`, so rejection_summary() named its verb "?" and, finding
no `result.error`, its code was lost. The RSI ratchet counted it as the persona's own rejection and scored all 663
world_incident sessions as baseline samples: the baselines of m01, m03 and m04 fell to 0.1458.
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None


def _command_result(ok, code=None):
    """Field-for-field noema_client 0.2.0's CommandResult for a WS ACT_RESULT frame. A refused command comes back as
    HTTP 200 with the error in the body (settle.ts commandResultHttpStatus), so protocol.py sets failure
    ACTION_REJECTED and keeps the server's code in `error`: the live "?:ACTION_REJECTED"."""
    body = {"ok": ok, "observation": {"play_text": "You enter."}} if ok else {
        "ok": False, "request_id": "r", "error": {"code": code, "message": "World is in INCIDENT."}}
    return SimpleNamespace(ok=ok, observation=body.get("observation"), error=body.get("error"), settled=None,
                           http_status=None, failure=None if ok else SimpleNamespace(value="ACTION_REJECTED"),
                           idempotency_key="k", request_id="r", world_status=None,
                           raw={"protocol": "agent-protocol/v1", "type": "ACT_RESULT", "request_id": "r", "body": body})


class OpeningEntryKeepsItsCode(unittest.TestCase):
    def test_refused_entry_is_counted_as_enter_world_with_its_code(self):
        from noema_orin.telemetry import rejection_summary

        turns = [_command_result(False, "WORLD_INCIDENT"),
                 SimpleNamespace(ok=False, reason=None, failure=SimpleNamespace(value="WORLD_INCIDENT"),
                                 proposal=SimpleNamespace(action="HARVEST", arguments={}), result=None)]
        out = rejection_summary(turns)["by_verb_code"]
        self.assertEqual(out, {"ENTER_WORLD:WORLD_INCIDENT": 1, "HARVEST:WORLD_INCIDENT": 1})
        self.assertNotIn("?:ACTION_REJECTED", out)

    def test_accepted_entry_is_not_a_rejection(self):
        from noema_orin.telemetry import rejection_summary

        self.assertEqual(rejection_summary([_command_result(True)])["by_verb_code"], {})

    def test_masked_entry_refusal_is_caught(self):
        """A body that says ok=false while the client says ok (noema-client#58) is a refusal here too."""
        from noema_orin.telemetry import rejection_summary

        entry = _command_result(True)
        entry.raw["body"] = {"ok": False, "observation": {}, "error": {"code": "PLAYER_UNAVAILABLE"}}
        entry.error = entry.raw["body"]["error"]
        self.assertEqual(rejection_summary([entry])["by_verb_code"], {"ENTER_WORLD:PLAYER_UNAVAILABLE": 1})

    def test_turn_results_are_unchanged(self):
        from noema_orin.telemetry import rejection_summary

        breaker = SimpleNamespace(ok=False, stopped=True, reason="BUDGET_EXCEEDED", failure=None, proposal=None,
                                  result=None)
        self.assertEqual(rejection_summary([breaker])["by_verb_code"], {"?:BUDGET_EXCEEDED": 1},
                         "a tripped breaker's stop entry is still a TurnResult without a proposal")

    def test_world_code_is_not_the_personas(self):
        from noema_orin.rsi import build_session_dossier
        from noema_orin.telemetry import rejection_summary

        rej = rejection_summary([_command_result(False, "WORLD_INCIDENT")])
        dossier = build_session_dossier(role="custodian", role_verbs={"REPAIR"}, turn_log=[{"action": "HARVEST"}],
                                        rejections=rej, stop_reason="world_incident")
        self.assertEqual((dossier["rejection_count"], dossier["world_failure_count"]), (0, 1))


@unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
class WorldEndedSessionIsNotScored(unittest.TestCase):
    """players.main() end to end, the real client, every command refused WORLD_INCIDENT, then SIGTERM."""

    def test_incident_session_gives_no_rsi_sample(self):
        import contextlib
        import io
        import json
        import signal
        import threading
        from unittest import mock

        from noema_client import client as client_mod
        from noema_client.config import StoredCredential
        from noema_client.errors import FailureClass
        from noema_client.types import CommandResult

        from noema_orin import planner, players

        observation = {
            "world_status": "INCIDENT", "world_name": "Perihelion Reach", "cycle": 23163, "sequence": 89945,
            "player_id": "player.Rivet-Custodian", "consequence": "",
            "location": {"room_id": "room.archive", "name": "Archive", "entities": [], "exits": []},
            "budgets": {"attention": 8, "compute": 64, "energy": 80, "influence": 40, "storage": 16},
            "available_actions": ["LOOK", "WAIT", "HARVEST"],
            "affordances": [{"action": "HARVEST", "available": True, "target_id": "entity.salvage-cache"}],
        }
        calls: list[str] = []
        killers: list[threading.Timer] = []

        def incident():
            return CommandResult(ok=False, observation=None,
                                 error={"code": "WORLD_INCIDENT", "message": "World is in INCIDENT."},
                                 settled=None, http_status=200, failure=FailureClass.WORLD_INCIDENT,
                                 idempotency_key="k", request_id="r", world_status="INCIDENT")

        class Gateway:
            def send_command(self, command, arguments=None, **_kw):
                calls.append(str(command).upper())
                if calls[-1] == "OBSERVE":
                    if not killers:
                        # the unit stops while it waits out the cooldown after the first session
                        killers.append(threading.Timer(2.0, os.kill, (os.getpid(), signal.SIGTERM)))
                        killers[-1].start()
                    return CommandResult(ok=True, observation=dict(observation), error=None, settled=True,
                                         http_status=200, failure=None, idempotency_key="k", request_id="r",
                                         world_status="INCIDENT")
                return incident()

            def close(self):
                return None

        class Client(client_mod.NoemaClient):
            def __init__(self, **kw):
                super().__init__("https://example.invalid", **kw)
                self._credential = StoredCredential(access_token="test-token")
                self._gateway = Gateway()

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "roles.tsv").write_text("m03\tcustodian\n")
            previous_handler = signal.getsignal(signal.SIGTERM)
            pinned = planner.PINNED_HOME
            out = io.StringIO()
            try:
                with mock.patch.dict(os.environ, {"NOEMA_LLM_BASE": "http://127.0.0.1:9/v1"}), \
                        mock.patch.object(client_mod, "NoemaClient", Client):
                    for key in ("NOEMA_TOKEN", "NOEMA_SERVER", "NOEMA_WORLD_ID", "NOEMA_ADMIN_TOKEN", "NOEMA_INFERENCE_MODE",
                                "NOEMA_LOCAL_LLM_BASE", "NOEMA_CONSEQUENCE_SHADOW", "NOEMA_TRT_EMBED_URL",
                                "NOEMA_TRANSITION_LOG", "MEMORY_SYNC_URL", "MEMORY_SYNC_TOKEN"):
                        os.environ.pop(key, None)
                    with contextlib.redirect_stdout(out):
                        rc = players.main(["--member", "m03", "--root", str(root), "--session-seconds", "20",
                                           "--cooldown", "12", "--turn-gap", "0.1"])
            finally:
                for killer in killers:
                    killer.join()
                signal.signal(signal.SIGTERM, previous_handler)
                planner.PINNED_HOME = pinned
            lines = [json.loads(x) for x in out.getvalue().splitlines() if x.startswith("{")]
            sessions = [x for x in lines if "stop_reason" in x]
            rsi_state = root / "m03" / "mind" / "rsi_state.json"
            samples = json.loads(rsi_state.read_text()).get("baseline_samples") if rsi_state.exists() else None

        self.assertEqual(rc, 0)
        self.assertEqual(len(sessions), 1, lines)
        session = sessions[0]
        self.assertEqual(session["stop_reason"], "world_incident")
        self.assertEqual(calls[0], "ENTER_WORLD")
        rej = session["rejections"]["by_verb_code"]
        self.assertNotIn("?:ACTION_REJECTED", rej)
        self.assertEqual(rej.get("ENTER_WORLD:WORLD_INCIDENT"), 1, rej)
        self.assertIsNone(session["rsi"], "the world ended this session: no fitness sample")
        self.assertEqual(session["reflection"], "skipped")
        self.assertFalse(samples, "the ratchet's baseline must not move on a world outage")


if __name__ == "__main__":
    unittest.main()
