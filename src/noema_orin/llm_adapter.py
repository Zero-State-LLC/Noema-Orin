"""DecisionAdapter over any ``propose(context) -> str`` callable (D-006).

Designed to wrap ``noema_llm_agent.llm.make_llm(...)``. Stdlib-only: the model
proposes, this adapter only parses, and the runner remains the validator.
"""

import json
import re
from typing import Callable, Mapping

_OBJECT = re.compile(r"\{[\s\S]*\}")
_INVALID: dict[str, object] = {"action": "INVALID", "target_id": None, "arguments": {"invalid": True}}


class ProposerAdapter:
    def __init__(self, propose: Callable[[dict[str, object]], str]) -> None:
        self._propose = propose

    def decide(self, observation: Mapping[str, object]) -> dict[str, object]:
        raw = self._propose({"canonical": dict(observation)})
        if type(raw) is not str:
            return dict(_INVALID)
        text = raw.strip()
        if not text.startswith("{"):
            found = _OBJECT.search(text)
            if not found:
                return dict(_INVALID)
            text = found.group(0)
        try:
            data = json.loads(text)
        except ValueError:
            return dict(_INVALID)
        if type(data) is not dict or type(data.get("action")) is not str:
            return dict(_INVALID)
        return {
            "action": data["action"].strip().upper(),
            "target_id": data.get("target_id"),
            "arguments": data.get("arguments", {}),
        }
