"""A one-command synthetic Controller runner; not a world client."""

from typing import Mapping

from .ports import CommandClient, DecisionAdapter
from .profiles import select
from .receipts import receipt


class ScriptedAdapter:
    def decide(self, observation: Mapping[str, object]) -> dict[str, object]:
        return {"action": "LOOK", "target_id": None, "arguments": {}}


class FakeClient:
    def __init__(self) -> None:
        self.attempts: list[dict[str, object]] = []

    def submit(self, proposal: Mapping[str, object]) -> object:
        self.attempts.append(dict(proposal))


def run(*, profile: str, fixture: Mapping[str, object] | None, client: CommandClient, adapter: DecisionAdapter) -> dict[str, object]:
    refusal = select(profile)
    if refusal is not None:
        return receipt("REFUSED", refusal)
    try:
        observation = fixture["observation"] if fixture is not None else None
        if not isinstance(observation, dict) or observation.get("synthetic") is not True:
            return receipt("REFUSED", "INVALID_FIXTURE", hosted=True)
    except (KeyError, TypeError, ValueError):
        return receipt("REFUSED", "INVALID_FIXTURE", hosted=True)
    try:
        proposal = adapter.decide(observation)
    except Exception:
        return receipt("REFUSED", "INVALID_PROPOSAL", hosted=True)
    if (not isinstance(proposal, dict) or set(proposal) != {"action", "target_id", "arguments"}
            or proposal["action"] != "LOOK" or proposal["target_id"] is not None or proposal["arguments"] != {}):
        return receipt("REFUSED", "INVALID_PROPOSAL", hosted=True)
    try:
        client.submit(proposal)
    except Exception:
        return receipt("FAILED_SUBMISSION", "TRANSPORT_FAILURE", hosted=True, handoff=True)
    return receipt("ATTEMPTED", "FAKE_HANDOFF", hosted=True, handoff=True)
