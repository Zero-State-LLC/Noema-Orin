"""A one-command synthetic Controller runner; not a world client."""

from typing import Mapping

from .ports import CommandClient, DecisionAdapter
from .profiles import select


class ScriptedAdapter:
    def decide(self, observation: Mapping[str, object]) -> dict[str, object]:
        return {"action": "LOOK", "target_id": None, "arguments": {}}


class FakeClient:
    def __init__(self) -> None:
        self.attempts: list[dict[str, object]] = []

    def submit(self, proposal: Mapping[str, object]) -> None:
        self.attempts.append(dict(proposal))


def run(*, profile: str, fixture: Mapping[str, object] | None, client: CommandClient, adapter: DecisionAdapter) -> dict[str, object]:
    refusal = select(profile)
    if refusal is not None:
        return {"status": "REFUSED", "result": refusal}
    try:
        observation = fixture["observation"] if fixture is not None else None
        if not isinstance(observation, dict) or observation.get("synthetic") is not True and observation != {}:
            return {"status": "REFUSED", "result": "INVALID_FIXTURE", "profile": "hosted"}
    except (KeyError, TypeError, ValueError):
        return {"status": "REFUSED", "result": "INVALID_FIXTURE", "profile": "hosted"}
    try:
        proposal = adapter.decide(observation)
    except Exception:
        return {"status": "REFUSED", "result": "INVALID_PROPOSAL", "profile": "hosted"}
    if (not isinstance(proposal, dict) or set(proposal) != {"action", "target_id", "arguments"}
            or proposal["action"] != "LOOK" or proposal["target_id"] is not None or proposal["arguments"] != {}):
        return {"status": "REFUSED", "result": "INVALID_PROPOSAL", "profile": "hosted"}
    try:
        client.submit(proposal)
    except Exception:
        return {"status": "FAILED_SUBMISSION", "result": "TRANSPORT_FAILURE", "profile": "hosted", "transport": "fake"}
    return {"status": "ATTEMPTED", "profile": "hosted", "transport": "fake"}
