"""D-099: SIGTERM ends a session at the next turn boundary.

Live (2026-11-28): every one of the 10 player stops in the journal ended in SIGKILL exactly 60 s after SIGTERM
(TimeoutStopSec=60). The handler only set `stop`, which the loop read between 30-minute sessions, and noema-client
0.2.0 sleeps between turns with time.sleep. Each old process took one more turn in its stop window, and each killed
session lost its outcome labels and its session line. players.py now takes the pause in PacedAdapter.decide(), on
the stop event, and declines the next turn once the unit is stopping.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from noema_orin.players import PacedAdapter

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None
REPO = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeStop:
    """threading.Event stand-in: a wait that isn't interrupted lets the clock run for the whole timeout."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.flag = False
        self.waits: list[float] = []

    def wait(self, timeout=None) -> bool:
        self.waits.append(timeout)
        if not self.flag and timeout:
            self.clock.now += timeout
        return self.flag

    def is_set(self) -> bool:
        return self.flag

    def set(self) -> None:
        self.flag = True


class Inner:
    def __init__(self, make=None) -> None:
        self.calls = 0
        self.make = make or (lambda: SimpleNamespace(action="WAIT"))

    def decide(self, _context):
        self.calls += 1
        return self.make()


class PacedAdapterTests(unittest.TestCase):
    def _paced(self, pause=20.0, duration=None):
        clock = Clock()
        stop = FakeStop(clock)
        inner = Inner()
        return PacedAdapter(inner, stop, pause, duration=duration, clock=clock), inner, stop, clock

    def test_first_turn_of_a_session_is_not_delayed(self):
        paced, inner, stop, _ = self._paced()
        self.assertIsNotNone(paced.decide({}))
        self.assertEqual((stop.waits, inner.calls), ([], 1), "the client never pauses before a session's first turn")

    def test_pause_between_turns_is_taken_on_the_stop_event(self):
        paced, inner, stop, clock = self._paced(pause=56)
        paced.decide({})
        paced.decide({})
        self.assertEqual((stop.waits, inner.calls, clock.now), ([56], 2, 56))

    def test_stopping_unit_declines_the_next_turn_without_asking_the_model(self):
        paced, inner, stop, _ = self._paced()
        paced.decide({})
        stop.set()
        self.assertIsNone(paced.decide({}))
        self.assertEqual((inner.calls, paced.declined), (1, "stop"))

    def test_stop_during_the_pause_ends_the_wait(self):
        stop = threading.Event()
        paced = PacedAdapter(Inner(), stop, 30)
        paced.decide({})
        timer = threading.Timer(0.1, stop.set)
        timer.start()
        began = time.monotonic()
        try:
            self.assertIsNone(paced.decide({}))
        finally:
            timer.join()
        self.assertLess(time.monotonic() - began, 5, "the old time.sleep pause ran for the full 30 s")

    def test_duration_declines_after_a_pause_like_the_client(self):
        paced, inner, _, clock = self._paced(pause=20, duration=60)
        taken = [paced.decide({}) is not None for _ in range(4)]
        self.assertEqual(taken, [True, True, True, False])
        self.assertEqual((inner.calls, paced.declined, clock.now), (3, "duration", 60))

    def test_begin_starts_a_fresh_session(self):
        paced, _, stop, clock = self._paced(pause=20, duration=60)
        for _ in range(4):
            paced.decide({})
        paced.begin()
        self.assertEqual((paced.decided, paced.declined, paced.started), (0, None, clock.now))
        waits_before = len(stop.waits)
        self.assertIsNotNone(paced.decide({}))
        self.assertEqual(len(stop.waits), waits_before, "no pause before the new session's first turn")

    def test_zero_pause_never_waits(self):
        paced, _, stop, _ = self._paced(pause=0)
        for _ in range(3):
            paced.decide({})
        self.assertEqual(stop.waits, [])


def _ok_result(observation=None):
    from noema_client.types import CommandResult

    return CommandResult(ok=True, observation=observation or {
        "world_status": "ACTIVE", "available_actions": ["LOOK", "WAIT"], "affordances": [], "consequence": "You wait."},
        error=None, settled=True, http_status=200, failure=None, idempotency_key="k", request_id="r",
        world_status="ACTIVE")


class OkGateway:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def send_command(self, command, arguments=None, **_kw):
        self.commands.append(str(command).upper())
        return _ok_result()

    def close(self) -> None:
        return None


def _client(tmp):
    from noema_client.client import NoemaClient

    c = NoemaClient(server="https://example.invalid", config_home=Path(tmp), transport="http")
    c._gateway = OkGateway()
    return c


def _waits(n):
    from noema_client.types import ActionProposal

    return [ActionProposal(action="WAIT") for _ in range(n)]


@unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
class PacedPlayTests(unittest.TestCase):
    """The real noema-client play() loop, with the pause moved out of it."""

    def test_same_turns_and_stop_as_the_clients_own_pause(self):
        from unittest import mock

        from noema_client import client as client_mod
        from noema_client.adapters.scripted import ScriptedAdapter
        from noema_client.types import StopReason

        for pause, duration in ((20, 60), (20, 61), (56, 1800), (7, 30)):
            with self.subTest(pause=pause, duration=duration), tempfile.TemporaryDirectory() as d:
                clock = Clock()

                def sleep(seconds):
                    clock.now += seconds

                with mock.patch.object(client_mod.time, "monotonic", clock), mock.patch.object(client_mod.time, "sleep", sleep):
                    native = _client(d).play(duration=duration, cooldown=pause, adapter=ScriptedAdapter(_waits(100)), enter=False)
                clock = Clock()
                paced = PacedAdapter(ScriptedAdapter(_waits(100)), FakeStop(clock), pause, duration=duration, clock=clock)
                report = paced.settle(_client(d).play(duration=duration, cooldown=0, adapter=paced, enter=False))
                self.assertEqual(native.stop_reason, StopReason.DURATION_ELAPSED)
                self.assertEqual((report.stop_reason, report.attempted, report.rejected, len(report)),
                                 (native.stop_reason, native.attempted, native.rejected, len(native)))

    def test_sigterm_ends_play_as_user_interrupt_with_no_declined_turn(self):
        from noema_client.types import ActionProposal, StopReason

        from noema_orin.telemetry import rejection_summary

        clock = Clock()
        stop = FakeStop(clock)

        def make():
            if inner.calls == 2:
                stop.set()  # SIGTERM lands while the second turn is in flight
            return ActionProposal(action="WAIT")

        inner = Inner(make)
        paced = PacedAdapter(inner, stop, 56, duration=1800, clock=clock)
        with tempfile.TemporaryDirectory() as d:
            client = _client(d)
            report = paced.settle(client.play(duration=1800, cooldown=0, adapter=paced))
        self.assertEqual((report.stop_reason, report.detail), (StopReason.USER_INTERRUPT, "SIGTERM"))
        self.assertEqual(report.as_dict()["stop_reason"], "user_interrupt")
        self.assertEqual((report.attempted, report.succeeded, report.rejected), (2, 2, 0))
        self.assertEqual(client._gateway.commands, ["ENTER_WORLD", "OBSERVE", "WAIT", "WAIT"])
        self.assertFalse(any(getattr(t, "reason", None) == "no_proposal" for t in report))
        self.assertEqual(rejection_summary(report)["by_verb_code"], {}, "the declined turn is not a rejection")

    def test_settle_leaves_other_stops_alone(self):
        from noema_client.types import PlayReport, StopReason, TurnResult

        paced = PacedAdapter(Inner(), FakeStop(Clock()), 20)
        incident = PlayReport([TurnResult(ok=False, stopped=True, reason="WORLD_INCIDENT")],
                              stop_reason=StopReason.WORLD_INCIDENT, attempted=1, rejected=1)
        self.assertIs(paced.settle(incident), incident)
        self.assertEqual((incident.stop_reason, len(incident), incident.attempted), (StopReason.WORLD_INCIDENT, 1, 1))
        paced.declined = "stop"  # stopping, but the world stopped the session first
        paced.settle(incident)
        self.assertEqual((incident.stop_reason, len(incident)), (StopReason.WORLD_INCIDENT, 1))


@unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
class SigtermEndsTheSessionInMain(unittest.TestCase):
    """players.main() end to end: the real session loop, the real client, a real SIGTERM, a fake gateway."""

    def test_sigterm_mid_session_exits_at_the_next_turn_with_the_session_labelled(self):
        import contextlib
        import io
        import json
        import signal
        from unittest import mock

        from noema_client import client as client_mod
        from noema_client.config import StoredCredential

        from noema_orin import planner, players

        observation = {
            "world_status": "ACTIVE", "world_name": "Perihelion Reach", "cycle": 23163, "sequence": 89945,
            "player_id": "player.Rivet-Custodian", "consequence": "You wait.",
            "location": {"room_id": "room.archive", "name": "Archive", "entities": [], "exits": []},
            "budgets": {"attention": 8, "compute": 64, "energy": 80, "influence": 40, "storage": 16},
            "available_actions": ["LOOK", "WAIT"], "affordances": [{"action": "WAIT", "available": True}],
        }
        calls: list[str] = []
        killers: list[threading.Timer] = []

        class Gateway:
            def send_command(self, command, arguments=None, **_kw):
                calls.append(str(command).upper())
                if len(calls) == 2:
                    # The OBSERVE that opens the session. Its first turn follows at once; by 1.5 s the unit is in
                    # the 12 s pause before the second.
                    killers.append(threading.Timer(1.5, os.kill, (os.getpid(), signal.SIGTERM)))
                    killers[-1].start()
                return _ok_result(dict(observation))

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
                with mock.patch.dict(os.environ, {"NOEMA_TRANSITION_LOG": "1", "NOEMA_LLM_BASE": "http://127.0.0.1:9/v1"}), \
                        mock.patch.object(client_mod, "NoemaClient", Client):
                    for key in ("NOEMA_TOKEN", "NOEMA_SERVER", "NOEMA_WORLD_ID", "NOEMA_ADMIN_TOKEN", "NOEMA_INFERENCE_MODE",
                                "NOEMA_LOCAL_LLM_BASE", "NOEMA_CONSEQUENCE_SHADOW", "NOEMA_TRT_EMBED_URL",
                                "MEMORY_SYNC_URL", "MEMORY_SYNC_TOKEN"):
                        os.environ.pop(key, None)
                    began = time.monotonic()
                    with contextlib.redirect_stdout(out):
                        rc = players.main(["--member", "m03", "--root", str(root), "--session-seconds", "20",
                                           "--cooldown", "12", "--turn-gap", "0.1"])
                    took = time.monotonic() - began
            finally:
                for killer in killers:
                    killer.join()
                signal.signal(signal.SIGTERM, previous_handler)
                planner.PINNED_HOME = pinned
            lines = [json.loads(x) for x in out.getvalue().splitlines() if x.startswith("{")]
            sessions = [x for x in lines if "stop_reason" in x]
            rows = [json.loads(x) for x in (root / "m03" / "mind" / "transitions.jsonl").read_text().splitlines()]

        self.assertEqual(rc, 0)
        self.assertLess(took, 8, "the old loop slept out the 12 s pause and played on until the session ended")
        self.assertEqual(len(sessions), 1, lines)
        session = sessions[0]
        self.assertEqual((session["stop_reason"], session["stop_detail"]), ("user_interrupt", "SIGTERM"))
        self.assertIsNone(session["rsi"], "a cut-short session gives the ratchet no fitness sample")
        self.assertEqual(session["reflection"], "skipped")
        self.assertNotIn("no_proposal", json.dumps(session["rejections"]))
        turns = [r for r in rows if "obs" in r]
        outcomes = [r for r in rows if r.get("kind") == "outcome"]
        self.assertEqual(len(turns), 1, "exactly one decided turn before the stop")
        self.assertEqual([(o["session"], o["turn"]) for o in outcomes], [(turns[0]["session"], 0)],
                         "the killed sessions were never labelled")


class RollingRestartGateTests(unittest.TestCase):
    """D-099: the gate counted log lines before `systemctl restart`, so the old process's turn in its stop window
    passed it. In the 11-28 11:58Z widen, each next unit was stopped exactly STAGGER_SECONDS (15 s) after the
    previous unit started: the gate passed at once, on the old process's turn. Three of the four new processes
    took their first turn 16 to 39 s after starting."""

    def _run(self, new_turn: bool):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "bin").mkdir()
            (d / "logs").mkdir()
            (d / "logs" / "noema-player@m03.log").write_text('{"turn": 7, "process": "old"}\n')
            fake = d / "bin" / "systemctl"
            fake.write_text(textwrap.dedent("""\
                #!/usr/bin/env bash
                # systemctl --user restart|is-active [--quiet] UNIT
                for unit; do :; done
                log="$LOG_DIR/$unit.log"
                if [[ "$2" == restart ]]; then
                  echo '{"turn": 8, "process": "old", "in": "stop window"}' >> "$log"
                  if [[ "$FAKE_NEW_TURN" == 1 ]]; then
                    ( sleep 0.5; echo '{"turn": 1, "process": "new"}' >> "$log" ) > /dev/null 2>&1 &
                  fi
                fi
                exit 0
            """))
            fake.chmod(0o755)
            env = dict(os.environ, PATH=f"{d / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}", LOG_DIR=str(d / "logs"),
                       UNITS="noema-player@m03", TURN_TIMEOUT="2", POLL_SECONDS="0.2", STAGGER_SECONDS="0",
                       FAKE_NEW_TURN="1" if new_turn else "0")
            return subprocess.run(["bash", str(REPO / "deploy" / "rolling-restart.sh"), "--apply"], env=env,
                                  capture_output=True, text=True, timeout=60)

    def test_old_process_turn_in_the_stop_window_does_not_pass_the_gate(self):
        done = self._run(new_turn=False)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("took no turn within 2s", done.stderr)

    def test_new_process_turn_passes_the_gate(self):
        done = self._run(new_turn=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("noema-player@m03 took a turn", done.stdout)


if __name__ == "__main__":
    unittest.main()
