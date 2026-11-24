"""T9: LLM-backed DecisionAdapter seam (D-006). Model proposes; runner still validates."""

import json
import unittest

from noema_orin.group import run_group
from noema_orin.llm_adapter import ProposerAdapter
from noema_orin.runner import FakeClient, run

FIXTURE = {"observation": {"synthetic": True, "available_actions": ["LOOK"]}}
SECRET = "SENTINEL_PROMPT_5521"


class ProposerAdapterTests(unittest.TestCase):
    def test_well_formed_look_is_submitted(self):
        seen = []
        def propose(context):
            seen.append(context)
            return json.dumps({"action": "look", "target_id": None, "arguments": {}})
        client = FakeClient()
        outcome = run(profile="hosted", fixture=FIXTURE, client=client, adapter=ProposerAdapter(propose))
        self.assertEqual(outcome["status"], "ATTEMPTED")
        self.assertEqual(client.attempts, [{"action": "LOOK", "target_id": None, "arguments": {}}])
        self.assertEqual(seen, [{"canonical": FIXTURE["observation"]}])

    def test_fenced_json_is_accepted(self):
        adapter = ProposerAdapter(lambda c: 'Sure:\n```json\n{"action":"LOOK","arguments":{}}\n```')
        self.assertEqual(run(profile="hosted", fixture=FIXTURE, client=FakeClient(), adapter=adapter)["status"], "ATTEMPTED")

    def test_non_look_or_garbage_refuses_before_client(self):
        for raw in ('{"action":"MOVE","arguments":{"to":"x"}}', "LOOK around", "", "[1]", '{"action":"LOOK","arguments":{"p":"' + SECRET + '"}}'):
            with self.subTest(raw=raw):
                client = FakeClient()
                outcome = run(profile="hosted", fixture=FIXTURE, client=client, adapter=ProposerAdapter(lambda c, r=raw: r))
                self.assertEqual(outcome["status"], "REFUSED")
                self.assertEqual(outcome["result"], "INVALID_PROPOSAL")
                self.assertEqual(client.attempts, [])
                self.assertNotIn(SECRET, json.dumps(outcome))

    def test_proposer_exception_is_refusal_without_echo(self):
        def boom(context):
            raise RuntimeError(SECRET)
        outcome = run(profile="hosted", fixture=FIXTURE, client=FakeClient(), adapter=ProposerAdapter(boom))
        self.assertEqual(outcome["result"], "INVALID_PROPOSAL")
        self.assertNotIn(SECRET, json.dumps(outcome))

    def test_group_members_get_independent_adapters(self):
        calls = []
        def factory(member_id):
            return ProposerAdapter(lambda c, m=member_id: calls.append(m) or '{"action":"LOOK","arguments":{}}')
        _, summary = run_group(profile="hosted", fixture=FIXTURE, size=6,
                               client_factory=lambda m: FakeClient(), adapter_factory=factory)
        self.assertEqual(summary["group_status"], "ATTEMPTED")
        self.assertEqual(calls, [f"member-{i:02d}" for i in range(1, 7)])


if __name__ == "__main__":
    unittest.main()
