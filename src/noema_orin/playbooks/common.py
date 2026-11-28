"""Shared playbook types and deterministic helpers (T8/#162)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PlaybookContext:
    adapter: Any
    canonical: dict[str, Any]
    options: list[dict[str, Any]]
    role_name: str
    room_id: str | None
    seq: int | None
    knobs: dict[str, Any]
    traits: dict[str, float]


@dataclass
class PlaybookResult:
    state: str
    proposal: Any | None = None
    note: str = ""


def route_to_room(ctx: PlaybookContext, goal_room: str) -> Any | None:
    """Emit one MOVE hop toward `goal_room` when reachable and affordable."""
    from noema_client.types import ActionProposal

    from ..orin_adapter import _can_afford_move

    wm = ctx.adapter.world_map
    if wm is None or not ctx.room_id or ctx.room_id == goal_room:
        return None
    if not _can_afford_move(ctx.canonical):
        return None
    if ctx.adapter.allowed and "MOVE" not in ctx.adapter.allowed:
        return None
    hop = wm.next_hop(ctx.room_id, goal_room)
    loc = ctx.canonical.get("location") or {}
    exits = {e.get("to_room_id"): e.get("direction") for e in loc.get("exits") or [] if isinstance(e, dict)}
    if hop in exits:
        ctx.adapter.dwell = 0
        return ActionProposal(action="MOVE", target_id=exits[hop])
    return None


def step_energy_and_recharge(ctx: PlaybookContext) -> PlaybookResult | None:
    """Shared survival gate: RECHARGE at ready generator, walk to generator, or WAIT-rest."""
    from noema_client.types import ActionProposal

    from ..orin_adapter import _can_afford_move, _depleted, _proposal
    from ..shop_planner import _room_has_ready_infra

    ad = ctx.adapter
    gen_ready = _room_has_ready_infra(ctx.canonical, "generator", min_condition=25) is not None
    if _depleted(ctx.canonical):
        rech = next((o for o in ctx.options if o["action"] == "RECHARGE"), None) if gen_ready else None
        if rech is not None:
            ad.dwell = 0
            return PlaybookResult("RECHARGE_DEPLETED", _proposal(rech, ad.default_args, ad.memory))
        ad.dwell = 0
        return PlaybookResult("WAIT_LOCKOUT_REST", ActionProposal(action="WAIT"))

    energy_now = (ctx.canonical.get("resources") or {}).get("energy")
    energy_floor = ad._effective_energy_floor()
    if isinstance(energy_now, (int, float)) and energy_now <= energy_floor:
        rech = next((o for o in ctx.options if o["action"] == "RECHARGE"), None) if gen_ready else None
        if rech is not None:
            ad.dwell = 0
            return PlaybookResult("RECHARGE_TOPUP", _proposal(rech, ad.default_args, ad.memory))
        wm = ad.world_map
        if (
            wm is not None
            and ctx.room_id
            and hasattr(wm, "where_offered")
            and _can_afford_move(ctx.canonical)
            and (not ad.allowed or "MOVE" in ad.allowed)
            and "RECHARGE" in (ad.allowed or {"RECHARGE"})
        ):
            goal = wm.where_offered({"RECHARGE"}, exclude=ctx.room_id, near=ctx.room_id)
            hops = (wm.distances(ctx.room_id) or {}).get(goal) if goal and hasattr(wm, "distances") else None
            if goal and hops and energy_now > hops:
                move = route_to_room(ctx, goal)
                if move is not None:
                    return PlaybookResult("ROUTE_GENERATOR", move)
    return None


def step_equipment(ctx: PlaybookContext) -> PlaybookResult | None:
    from ..shop_planner import plan_equipment_step

    if ctx.role_name not in ("founder", "quartermaster", "custodian", "archivist", "speaker", "surveyor"):
        return None
    prop = plan_equipment_step(
        ctx.role_name,
        ctx.canonical,
        ctx.knobs,
        allowed_actions=getattr(ctx.adapter, "allowed", None) or None,
        world_map=ctx.adapter.world_map,
    )
    if prop is not None and hasattr(prop, "action"):
        ctx.adapter.dwell = 0
        return PlaybookResult("EQUIPMENT_UPKEEP", prop)
    return None


def step_scar_attest(ctx: PlaybookContext) -> PlaybookResult | None:
    from ..orin_adapter import _proposal

    ad = ctx.adapter
    if "ATTEST" in ad.verbs and "RECONSTRUCT" not in ad.verbs and (ctx.canonical.get("scars") or []):
        attested = getattr(ad, "_attested_targets", set())
        att_opt = next(
            (o for o in ctx.options if o["action"] == "ATTEST" and str(o.get("target_id") or "") not in attested),
            None,
        )
        if att_opt is not None:
            ad.dwell = 0
            if not hasattr(ad, "_attested_targets"):
                ad._attested_targets = set()
            ad._attested_targets.add(str(att_opt.get("target_id") or ""))
            return PlaybookResult("SCAR_ATTEST", _proposal(att_opt, ad.default_args, ad.memory))
    return None


def step_agenda_route(ctx: PlaybookContext) -> PlaybookResult | None:
    """If an active medium-loop AgendaStep names a remote target_room and no role work is here, step toward it."""
    mgr = getattr(ctx.adapter, "agenda_manager", None)
    if mgr is None or ctx.seq is None:
        return None
    step = mgr.active_step(int(ctx.seq))
    if step is None or not step.target_room or step.target_room == ctx.room_id:
        return None
    move = route_to_room(ctx, step.target_room)
    if move is not None:
        return PlaybookResult(f"AGENDA_ROUTE:{step.goal_kind}", move)
    return None


def step_supply_and_dwell_route(ctx: PlaybookContext) -> PlaybookResult | None:
    """Shared resource starvation, build/supply spend, agenda routing, and dwell-gated world-map routing."""
    from noema_client.types import ActionProposal

    from ..orin_adapter import (
        SPEND_READY,
        _can_afford_move,
        _hold_empty,
        _hold_ready,
        _offered_here,
        _proposal,
        _route_verbs,
        _starved_for_attention,
        _wait_refuels,
    )
    from ..planner import has_role_verb, route

    ad = ctx.adapter
    canonical = ctx.canonical
    options = ctx.options
    goal_verbs = ad.verbs
    if ad.supply and _hold_empty(canonical):
        goal_verbs = ad.supply
    if _starved_for_attention(canonical, goal_verbs):
        ad.dwell = 0
        return PlaybookResult("WAIT_BUDGET_STARVED", ActionProposal(action="WAIT"))

    here = has_role_verb(options, goal_verbs) or _offered_here(canonical, goal_verbs, done=ad._published_subjects())
    energy = (canonical.get("resources") or {}).get("energy")
    if ad.supply and not _hold_empty(canonical) and not here and isinstance(energy, (int, float)) and energy < SPEND_READY:
        ad.dwell = 0
        return PlaybookResult("WAIT_SPEND_READY", ActionProposal(action="WAIT"))

    if (
        not here
        and ad.world_map is not None
        and not _wait_refuels(canonical.get("resources") or {})
        and _can_afford_move(canonical)
        and (not ad.allowed or "MOVE" in ad.allowed)
    ):
        direction = route(
            canonical,
            ad.world_map,
            _route_verbs(goal_verbs),
            explorer=ad.explorer,
            me=getattr(ad, "self_id", None),
            current_seq=ctx.seq,
        )
        if direction:
            ad.dwell = 0
            return PlaybookResult("ROUTE_EMPTY_HOLD", ActionProposal(action="MOVE", target_id=direction))

    if ad.builds and _hold_ready(canonical):
        # D-094: a class already built is not built again (`prefer_builds` drops its CONSTRUCT), so never wait for it.
        built = ad._built_classes() if hasattr(ad, "_built_classes") else set()
        want = tuple(b for b in ad.builds if b not in built)
        pick = next(
            (o for o in options if o["action"] == "CONSTRUCT" and str((o.get("raw") or {}).get("class") or "") in ad.builds),
            None,
        )
        if pick is not None:
            return PlaybookResult("CONSTRUCT_ROLE_SPACE", _proposal(pick, ad.default_args, ad.memory))
        blocked = [
            a for a in canonical.get("affordances") or []
            if isinstance(a, dict)
            and str(a.get("operation") or "").upper() == "CONSTRUCT"
            and a.get("available") is False
            and str(a.get("class") or "") in want
            and "materials" not in str(a.get("reason") or "")
        ]
        if blocked and "HARVEST" in (ad.verbs | set(ad.supply or ())):
            ad.dwell = 0
            return PlaybookResult("WAIT_BUILD_ENERGY", ActionProposal(action="WAIT"))

    if ad.supply and _hold_empty(canonical):
        pick = next((o for o in options if o["action"] in ad.supply), None)
        if pick is not None:
            ad.dwell = 0
            return PlaybookResult("GATHER_SUPPLY", _proposal(pick, ad.default_args, ad.memory))
    elif ad.supply:
        pick = next((o for o in options if o["action"] in ad.verbs and o["action"] not in ad.supply), None)
        if pick is not None:
            ad.dwell = 0
            return PlaybookResult("SPEND_CARGO", _proposal(pick, ad.default_args, ad.memory))

    dwell_limit = ad._effective_dwell_limit()
    if ad.world_map is None or here or ad.dwell < dwell_limit or (ad.allowed and "MOVE" not in ad.allowed):
        ad.dwell = ad.dwell + 1 if not here else 0
        return None
    if not _can_afford_move(canonical):
        return PlaybookResult("WAIT_MOVE_ENERGY", ActionProposal(action="WAIT"))

    ag = step_agenda_route(ctx)
    if ag is not None:
        return ag

    avoid_p = "SUPPLY" in ad.verbs and float(ctx.knobs.get("scar_avoidance_weight", 0.7)) >= 0.5
    seek_s = "RECONSTRUCT" in ad.verbs
    direction = route(
        canonical,
        ad.world_map,
        _route_verbs(goal_verbs),
        explorer=ad.explorer,
        me=getattr(ad, "self_id", None),
        avoid_pressure=avoid_p,
        pressure_weight=float(ctx.knobs.get("scar_avoidance_weight", 0.7)),
        seek_scars=seek_s,
        current_seq=ctx.seq,
    )
    if not direction:
        return None
    ad.dwell = 0
    return PlaybookResult("ROUTE_ROLE_VERB", ActionProposal(action="MOVE", target_id=direction))
