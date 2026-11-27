"""T10 (#164) local CUDA llama-server + JSON schema grammar + S1/S2 routing, and T11 (#165) grounded voice verifier."""
from __future__ import annotations

import http.server
import json
import threading
import unittest
from unittest.mock import patch

from noema_orin.health import RoleHealthTracker
from noema_orin.llm_client import (
    build_choice_schema,
    build_voice_schema,
    call_llama_server,
)
from noema_orin.voice import (
    FactBundle,
    GroundedFact,
    synthesize_grounded_utterance,
    verify_grounded_utterance,
)


class _FakeLlamaHandler(http.server.BaseHTTPRequestHandler):
    seen_payloads: list[dict] = []
    next_response: dict = {"choice": 1, "why": "repair relay"}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        self.__class__.seen_payloads.append(body)
        resp = {
            "choices": [
                {"message": {"content": json.dumps(self.__class__.next_response)}}
            ]
        }
        raw = json.dumps(resp).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format, *args):
        return


class LlamaServerAndRoutingTests(unittest.TestCase):
    def test_choice_and_voice_schemas_constrain_enums(self):
        cs = build_choice_schema(4)
        self.assertEqual(cs["type"], "json_schema")
        props = cs["json_schema"]["schema"]["properties"]
        self.assertEqual(props["choice"]["enum"], [0, 1, 2, 3])

        vs = build_voice_schema([101, 205])
        vprops = vs["json_schema"]["schema"]["properties"]
        self.assertEqual(vprops["cited_seqs"]["items"]["enum"], [101, 205])

    def test_call_llama_server_sends_response_format_and_parses_json(self):
        _FakeLlamaHandler.seen_payloads = []
        _FakeLlamaHandler.next_response = {"choice": 2, "why": "repair damaged relay"}
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _FakeLlamaHandler)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            url = f"http://127.0.0.1:{srv.server_address[1]}/v1"
            out = call_llama_server(
                base_url=url,
                model="qwen2.5-3b-instruct-q4_k_m",
                system="Pick option",
                user="{}",
                response_format=build_choice_schema(3),
                max_tokens=48,
                timeout=5.0,
            )
            self.assertEqual(out, {"choice": 2, "why": "repair damaged relay"})
            self.assertEqual(len(_FakeLlamaHandler.seen_payloads), 1)
            sent = _FakeLlamaHandler.seen_payloads[0]
            self.assertEqual(sent["response_format"]["type"], "json_schema")
            self.assertEqual(sent["response_format"]["json_schema"]["schema"]["properties"]["choice"]["enum"], [0, 1, 2])
        finally:
            srv.shutdown()
            srv.server_close()

    def test_health_tracker_distinguishes_intentional_local_s1_from_fallbacks(self):
        tracker = RoleHealthTracker(role="Rivet-Custodian")
        tracker.record_turn(verb="REPAIR", used_workers_ai=False, used_local_s1=True, source_sequence=10)
        tracker.record_turn(verb="REPAIR", used_workers_ai=False, used_local_s1=True, source_sequence=11)
        tracker.record_turn(verb="HARVEST", used_workers_ai=True, source_sequence=12)
        summary = tracker.summary()
        self.assertEqual(summary["local_s1_calls"], 2)
        self.assertEqual(summary["workers_ai_calls"], 1)
        self.assertEqual(summary["ollama_fallbacks"], 0)
        self.assertEqual(summary["fallback_ratio"], 0.0)


class GroundedCharacterVoiceTests(unittest.TestCase):
    def _bundle(self) -> FactBundle:
        return FactBundle(
            facts=(
                GroundedFact(
                    text="Exchange stall offers power_cell for 3 FERROUS_ORE",
                    seq=512,
                    room_id="room.civic-exchange",
                    entity_id="entity.stall-1",
                    numbers=(3,),
                ),
            ),
            fallback_text="Reach Compact notice: Exchange stall offers power_cell for 3 FERROUS_ORE (observed at seq 512)",
        )

    def test_verifier_accepts_grounded_utterance_and_rejects_hallucinations_and_leaks(self):
        bundle = self._bundle()
        good = "Civic Exchange: power_cell available at the barter stall for 3 ferrous ore (observed at seq 512)."
        ok, reason = verify_grounded_utterance(good, bundle)
        self.assertTrue(ok, reason)

        # Hallucinated sequence -> rejected
        bad_seq = "Civic Exchange: power_cell for 3 ore (observed at seq 999)."
        ok_seq, r_seq = verify_grounded_utterance(bad_seq, bundle)
        self.assertFalse(ok_seq)
        self.assertIn("seq", r_seq)

        # Wrong price/number -> rejected
        bad_num = "Civic Exchange: power_cell for 99 ore (observed at seq 512)."
        ok_num, r_num = verify_grounded_utterance(bad_num, bundle)
        self.assertFalse(ok_num)
        self.assertIn("number", r_num)

        # Leaked private cognition terms (ADR-0002) -> rejected
        leak = "Civic Exchange: my policy_knobs say power_cell is 3 ore (observed at seq 512)."
        ok_leak, r_leak = verify_grounded_utterance(leak, bundle)
        self.assertFalse(ok_leak)
        self.assertIn("private", r_leak)

        # Oversized (>280 chars) -> rejected
        too_long = ("A" * 270) + " (observed at seq 512)"
        ok_len, _ = verify_grounded_utterance(too_long, bundle)
        self.assertFalse(ok_len)

    def test_synthesize_grounded_utterance_falls_back_on_invalid_model_output(self):
        bundle = self._bundle()
        persona = {
            "name": "Cantor",
            "role": "speaker",
            "voice": "warm, rhythmic",
            "value": "news grounded or not at all",
            "quirk": "opens with the room name",
            "traits": {"sociability": 0.9},  # must NEVER enter prompt
        }
        seen_prompts = []

        def fake_llm(system: str, user: str, response_format: dict):
            seen_prompts.append((system, user))
            return {"utterance": "Civic Exchange: power_cell for 3 ore (observed at seq 512).", "cited_seqs": [512]}

        text, used_llm = synthesize_grounded_utterance(persona, bundle, llm_fn=fake_llm)
        self.assertTrue(used_llm)
        self.assertIn("observed at seq 512", text)
        # Ensure private traits never entered prompt
        self.assertNotIn("sociability", seen_prompts[0][0] + seen_prompts[0][1])

        # Hallucinating model -> deterministic fallback
        def bad_llm(system: str, user: str, response_format: dict):
            return {"utterance": "Free power_cell for 0 ore (observed at seq 777)!", "cited_seqs": [777]}

        fb_text, used_llm2 = synthesize_grounded_utterance(persona, bundle, llm_fn=bad_llm)
        self.assertFalse(used_llm2)
        self.assertEqual(fb_text, bundle.fallback_text)


if __name__ == "__main__":
    unittest.main()
