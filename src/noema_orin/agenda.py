"""Medium-loop agenda planner (T9/#163): 3-5 typed sub-goals surviving 30-min session restarts.

Synthesizes concrete sub-goals from controller-local `shared/map.db` (shared_work,
observed_listings, observed_equipment, scarred_rooms, cohort_claims) weighted by
`persona_traits`. Never enters wire payloads (`ADR-0002`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .rsi import load_agenda, save_agenda

AGENDA_REFRESH_TURNS = 10
MAX_AGENDA_STEPS = 5
STEP_TTL_SEQS = 40

GOAL_COMPLETION_VERBS: dict[str, set[str]] = {
    "REPAIR_INFRA": {"REPAIR", "RESTORE", "REMEDIATE", "CONTRACT_FULFILL"},
    "CRAFT_FOR_FLEET": {"CRAFT", "CONTRACT_FULFILL"},
    "RESTOCK_STALL": {"TRADE", "CONSTRUCT"},
    "SUPPLY_PEER": {"SUPPLY"},
    "POST_CONTRACT": {"CONTRACT_POST", "ORG_GOVERNANCE_RULE"},
    "INSPECT_SCAR": {"RECONSTRUCT", "RECONSTRUCT_PUBLISH", "RECONSTRUCT_SUPERSEDE", "ATTEST", "COMMEMORATE"},
    "HERALD_DIGEST": {"ORG_OFFICE_ACT", "BOARD", "SHOUT"},
    "SURVEY_FRONTIER": {"MOVE", "HARVEST", "ATTEST", "CONNECT"},
}


@dataclass
class AgendaStep:
    goal_kind: str
    target_room: str | None = None
    target_id: str | None = None
    status: str = "pending"  # pending | active | done | blocked
    created_seq: int = 0
    expires_seq: int = 0
    priority: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: object) -> "AgendaStep | None":
        if not isinstance(raw, dict) or not raw.get("goal_kind"):
            return None
        return cls(
            goal_kind=str(raw["goal_kind"]),
            target_room=str(raw["target_room"]) if raw.get("target_room") else None,
            target_id=str(raw["target_id"]) if raw.get("target_id") else None,
            status=str(raw.get("status") or "pending"),
            created_seq=int(raw.get("created_seq") or 0),
            expires_seq=int(raw.get("expires_seq") or 0),
            priority=float(raw.get("priority") or 0.5),
        )


class AgendaManager:
    """Stateful medium-loop agenda backed by `mind/agenda.json`."""

    def __init__(
        self,
        *,
        epoch: int = 0,
        steps: list[AgendaStep] | None = None,
        last_refresh_turn: int = -AGENDA_REFRESH_TURNS,
        updated_seq: int = 0,
    ) -> None:
        self.epoch = int(epoch)
        self.steps: list[AgendaStep] = list(steps or [])[:MAX_AGENDA_STEPS]
        self.last_refresh_turn = int(last_refresh_turn)
        self.updated_seq = int(updated_seq)

    @classmethod
    def from_disk(cls, mind: Path) -> "AgendaManager":
        data = load_agenda(mind)
        parsed: list[AgendaStep] = []
        for raw in data.get("steps") or []:
            step = AgendaStep.from_dict(raw)
            if step is not None:
                parsed.append(step)
        return cls(
            epoch=int(data.get("epoch") or 0),
            steps=parsed,
            updated_seq=int(data.get("updated_seq") or 0),
        )

    def save(
        self,
        mind: Path,
        *,
        held_tracks: list[str] | None = None,
        build_room: str | None = None,
        updated_seq: int | None = None,
    ) -> None:
        seq = self.updated_seq if updated_seq is None else int(updated_seq)
        save_agenda(
            mind,
            {
                "held_tracks": list(held_tracks or []),
                "build_room": build_room,
                "epoch": self.epoch,
                "steps": [s.to_dict() for s in self.steps[:MAX_AGENDA_STEPS]],
                "updated_seq": seq,
            },
        )

    def active_step(self, current_seq: int) -> AgendaStep | None:
        """Return the highest-priority unexpired pending/active step, marking overdue ones blocked."""
        seq = int(current_seq or 0)
        for step in self.steps:
            if step.status in ("done", "blocked"):
                continue
            if step.expires_seq > 0 and seq >= step.expires_seq:
                step.status = "blocked"
                continue
            step.status = "active"
            return step
        return None

    def needs_refresh(self, turn_count: int, current_seq: int) -> bool:
        if self.active_step(current_seq) is None:
            return True
        return (int(turn_count) - self.last_refresh_turn) >= AGENDA_REFRESH_TURNS

    def mark_progress(
        self,
        *,
        canonical: dict[str, Any],
        action: str,
        target_id: str | None,
        current_seq: int,
    ) -> None:
        step = self.active_step(current_seq)
        if step is None:
            return
        act = str(action or "").upper()
        room = (canonical.get("location") or {}).get("room_id")
        verbs = GOAL_COMPLETION_VERBS.get(step.goal_kind, set())
        room_ok = step.target_room is None or room == step.target_room
        target_ok = step.target_id is None or target_id is None or str(target_id) == step.target_id
        if act in verbs and room_ok and target_ok:
            step.status = "done"

    def refresh(
        self,
        *,
        role: str,
        canonical: dict[str, Any],
        world_map,
        traits: dict[str, float] | None,
        current_seq: int,
        turn_count: int = 0,
        me: str | None = None,
        llm_refiner: Callable[[list[AgendaStep]], int | None] | None = None,
    ) -> list[AgendaStep]:
        """Build 3-5 prioritized concrete sub-goals from shared/map.db and persona traits."""
        seq = int(current_seq or 0)
        exp = seq + STEP_TTL_SEQS
        t = traits or {}
        curiosity = float(t.get("curiosity", 0.5))
        thrift = float(t.get("thrift", 0.5))
        sociability = float(t.get("sociability", 0.5))
        here = (canonical.get("location") or {}).get("room_id")
        claimed = (
            set(world_map.active_claims(seq, exclude_member=me))
            if world_map is not None and hasattr(world_map, "active_claims")
            else set()
        )
        candidates: list[AgendaStep] = []

        if role == "custodian" and world_map is not None:
            if hasattr(world_map, "shared_work"):
                for row in world_map.shared_work({"REPAIR", "REMEDIATE"}, exclude_targets=claimed)[:3]:
                    sev = 1.0 - (int(row.get("condition") if row.get("condition") is not None else 50) / 100.0)
                    candidates.append(
                        AgendaStep(
                            goal_kind="REPAIR_INFRA",
                            target_room=row["room_id"],
                            target_id=row["target_id"],
                            created_seq=seq,
                            expires_seq=exp,
                            priority=round(0.7 + sev * 0.3, 3),
                        )
                    )
            candidates.append(
                AgendaStep(
                    goal_kind="CRAFT_FOR_FLEET",
                    target_room="room.civic-exchange",
                    created_seq=seq,
                    expires_seq=exp,
                    priority=round(0.5 + thrift * 0.2, 3),
                )
            )
        elif role == "quartermaster":
            candidates.append(
                AgendaStep(
                    goal_kind="RESTOCK_STALL",
                    target_room="room.civic-exchange",
                    created_seq=seq,
                    expires_seq=exp,
                    priority=round(0.75 + thrift * 0.2, 3),
                )
            )
            candidates.append(
                AgendaStep(
                    goal_kind="SUPPLY_PEER",
                    target_room=None,
                    created_seq=seq,
                    expires_seq=exp,
                    priority=round(0.6 + sociability * 0.2, 3),
                )
            )
        elif role == "founder":
            candidates.append(
                AgendaStep(
                    goal_kind="POST_CONTRACT",
                    target_room="room.civic-exchange",
                    created_seq=seq,
                    expires_seq=exp,
                    priority=round(0.75 + sociability * 0.15, 3),
                )
            )
        elif role == "archivist" and world_map is not None:
            if hasattr(world_map, "scarred_rooms"):
                for r in world_map.scarred_rooms(near=here)[:3]:
                    candidates.append(
                        AgendaStep(
                            goal_kind="INSPECT_SCAR",
                            target_room=r,
                            created_seq=seq,
                            expires_seq=exp,
                            priority=round(0.7 + curiosity * 0.25, 3),
                        )
                    )
        elif role == "speaker":
            candidates.append(
                AgendaStep(
                    goal_kind="HERALD_DIGEST",
                    target_room="room.civic-exchange",
                    created_seq=seq,
                    expires_seq=exp,
                    priority=round(0.7 + sociability * 0.25, 3),
                )
            )
        elif role == "surveyor":
            candidates.append(
                AgendaStep(
                    goal_kind="SURVEY_FRONTIER",
                    target_room=None,
                    created_seq=seq,
                    expires_seq=exp,
                    priority=round(0.7 + curiosity * 0.25, 3),
                )
            )

        candidates.sort(key=lambda s: (-s.priority, s.goal_kind, str(s.target_room or "")))
        candidates = candidates[:MAX_AGENDA_STEPS]
        if llm_refiner is not None and len(candidates) > 1:
            try:
                pick = llm_refiner(candidates)
                if type(pick) is int and 0 <= pick < len(candidates):
                    chosen = candidates.pop(pick)
                    candidates.insert(0, chosen)
            except Exception:
                pass
        if candidates:
            candidates[0].status = "active"
        self.steps = candidates
        self.epoch += 1
        self.last_refresh_turn = int(turn_count)
        self.updated_seq = seq
        return list(self.steps)
