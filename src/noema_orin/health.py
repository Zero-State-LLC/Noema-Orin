"""Workers AI circuit-breaker and per-role idle/fallback health telemetry (D-016)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkersAICircuitBreaker:
    """Short-circuits Workers AI calls after consecutive failures until cooldown elapses."""

    failure_threshold: int = 3
    cooldown_seconds: float = 60.0
    consecutive_failures: int = 0
    open_until_ts: float = 0.0

    def allow_remote(self, now_ts: float) -> bool:
        return now_ts >= self.open_until_ts

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.open_until_ts = 0.0

    def record_failure(self, now_ts: float) -> bool:
        """Record a failure; returns True if the breaker opened on this failure."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_threshold:
            self.open_until_ts = now_ts + self.cooldown_seconds
            return True
        return False


@dataclass
class RoleHealthTracker:
    """Tracks per-role active vs. idle turns and Workers AI vs. Ollama fallback counts."""

    role: str
    active_turns: int = 0
    idle_turns: int = 0
    workers_ai_calls: int = 0
    planner_turns: int = 0
    ollama_fallbacks: int = 0
    error_count: int = 0
    last_source_sequence: int = 0
    _recent_verbs: list[str] = field(default_factory=list)

    def record_turn(
        self,
        *,
        verb: str,
        used_workers_ai: bool,
        source_sequence: int,
        had_error: bool = False,
        used_planner: bool = False,
        used_local: bool | None = None,
    ) -> None:
        norm = verb.strip().upper()
        if norm in {"LOOK", "WAIT"}:
            self.idle_turns += 1
        else:
            self.active_turns += 1
        if used_planner:
            self.planner_turns += 1
        elif used_workers_ai:
            self.workers_ai_calls += 1
        elif used_local is None or used_local:
            # D-075: scripted fallback/loop_break turns call no model; only count real local-model calls.
            self.ollama_fallbacks += 1
        if had_error:
            self.error_count += 1
        if source_sequence > self.last_source_sequence:
            self.last_source_sequence = source_sequence
        self._recent_verbs.append(norm)
        if len(self._recent_verbs) > 20:
            self._recent_verbs.pop(0)

    def summary(self) -> dict[str, object]:
        total = self.active_turns + self.idle_turns
        idle_ratio = round(self.idle_turns / total, 3) if total else 0.0
        total_llm = self.workers_ai_calls + self.ollama_fallbacks
        fallback_ratio = round(self.ollama_fallbacks / total_llm, 3) if total_llm else 0.0
        return {
            "role": self.role,
            "total_turns": total,
            "active_turns": self.active_turns,
            "idle_turns": self.idle_turns,
            "idle_ratio": idle_ratio,
            "workers_ai_calls": self.workers_ai_calls,
            "planner_turns": self.planner_turns,
            "ollama_fallbacks": self.ollama_fallbacks,
            "fallback_ratio": fallback_ratio,
            "error_count": self.error_count,
            "last_source_sequence": self.last_source_sequence,
        }
