"""Controller decision and command seams for synthetic testing."""

from typing import Any, Mapping, Protocol


class DecisionAdapter(Protocol):
    def decide(self, observation: Mapping[str, object]) -> Mapping[str, object]: ...


class CommandClient(Protocol):
    def submit(self, proposal: Mapping[str, object]) -> Any: ...
