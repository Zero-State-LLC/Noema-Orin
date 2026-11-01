"""A one-command synthetic Controller runner; not a world client."""

from typing import Mapping

from .ports import CommandClient, DecisionAdapter


class ScriptedAdapter:
    def decide(self, observation: Mapping[str, object]) -> dict[str, object]:
        return {"action": "LOOK", "target_id": None, "arguments": {}}


class FakeClient:
    def __init__(self) -> None:
        self.attempts: list[dict[str, object]] = []

    def submit(self, proposal: Mapping[str, object]) -> None:
        self.attempts.append(dict(proposal))


def run(*, profile: str, fixture: Mapping[str, object], client: CommandClient, adapter: DecisionAdapter) -> dict[str, object]:
    if profile != "hosted":
        raise ValueError("only the hosted synthetic target is available")
    observation = fixture["observation"]
    if not isinstance(observation, dict):
        raise ValueError("invalid fixture observation")
    proposal = adapter.decide(observation)
    client.submit(proposal)
    return {"status": "ATTEMPTED", "profile": "hosted", "transport": "fake"}
