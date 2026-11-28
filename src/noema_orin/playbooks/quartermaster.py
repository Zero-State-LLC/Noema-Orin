"""m02 Tallow-Quartermaster declarative playbook: EQUIPMENT -> STOREFRONT -> SUPPLY -> BUILD -> FALLOW_HARVEST."""

from __future__ import annotations

from ..planner import home_org
from ..shop_planner import plan_quartermaster_shop, quartermaster_needs_shop_visit, storefront_room
from .common import PlaybookContext, PlaybookResult, route_to_room, step_equipment


def run_quartermaster_playbook(ctx: PlaybookContext) -> PlaybookResult | None:
    from noema_client.types import ActionProposal

    from ..orin_adapter import (
        _can_afford_move,
        _can_supply,
        _needs_supply,
        _proposal,
        _toward_needy_custodian,
        _treasury_build_waiting,
        _vault_harvest_amount,
        _vault_storage,
        _wait_refuels,
    )

    ad = ctx.adapter
    canonical = ctx.canonical
    options = ctx.options

    eq = step_equipment(ctx)
    if eq is not None:
        return eq

    shop_prop = plan_quartermaster_shop(canonical, ctx.knobs, recent_actions=getattr(ad, "recent", None))
    if shop_prop is not None and hasattr(shop_prop, "action"):
        ad.dwell = 0
        return PlaybookResult("STOREFRONT", shop_prop)

    # D-092: serve a colocated peer with recorded need before walking anywhere. m02 walked to the custodian
    # (SEEK_CUSTODIAN), arrived with SUPPLY on offer, and RETURN_STOREFRONT pulled it straight back.
    custodian = ad.role_handles.get("custodian")
    served = {r.get("target") for r in getattr(ad, "recent", [])[-10:] if r["action"] == "SUPPLY"}
    for o in options:
        if "SUPPLY" in ad.verbs and o["action"] == "SUPPLY" and o.get("target_id") not in served:
            if _needs_supply(o, custodian, ad.world_map, ad.cohort_ids):
                ok_sup, sup_amt = _can_supply(o, canonical)
                if ok_sup:
                    ad.dwell = 0
                    p = _proposal(o, ad.default_args, ad.memory)
                    if p is not None:
                        p.arguments = {**(p.arguments or {}), "amount": sup_amt}
                        if ad.memory is not None and p.target_id:
                            ad.memory.note_player(str(p.target_id), "supplied cargo from treasury", sign=1, sequence=ctx.seq)
                    return PlaybookResult("SUPPLY_PEER", p)

    home_id = home_org(canonical)
    if quartermaster_needs_shop_visit(canonical, ad.world_map, ctx.knobs, home_id):
        move = route_to_room(ctx, storefront_room(ad.world_map, home_id))
        if move is not None:
            return PlaybookResult("RETURN_STOREFRONT", move)

    vault = next((o for o in options if "SUPPLY" in ad.verbs and o["action"] == "HARVEST" and (o.get("raw") or {}).get("acting_for")), None)
    tbuild = next(
        (
            o for o in options
            if "SUPPLY" in ad.verbs
            and o["action"] in ("CONSTRUCT", "BUILD")
            and (o.get("raw") or {}).get("acting_for")
            and str((o.get("raw") or {}).get("class") or "") in ad.builds
        ),
        None,
    )
    treasury_floor = ad._effective_treasury_floor()
    if tbuild is not None and _vault_storage(canonical) >= treasury_floor:
        ad.dwell = 0
        return PlaybookResult("TREASURY_BUILD", _proposal(tbuild, ad.default_args, ad.memory))
    if (
        "SUPPLY" in ad.verbs
        and _vault_storage(canonical) >= treasury_floor
        and _treasury_build_waiting(canonical, ad.builds)
        and _wait_refuels(canonical.get("resources") or {})
    ):
        ad.dwell = 0
        return PlaybookResult("WAIT_TREASURY_BUILD_FUEL", ActionProposal(action="WAIT"))

    fuel = ad._fuel_for_build(canonical, options) if "SUPPLY" in ad.verbs else None
    if fuel is not None:
        ad.dwell = 0
        return PlaybookResult("COLLECT_BUILD_FUEL", fuel)

    step = _toward_needy_custodian(canonical, custodian, ad.world_map) if "SUPPLY" in ad.verbs else None
    if step is not None and _can_afford_move(canonical):
        ad.dwell = 0
        return PlaybookResult("SEEK_CUSTODIAN", ActionProposal(action="MOVE", target_id=step))

    if vault is not None:
        scar_w = float(ctx.knobs.get("scar_avoidance_weight", 0.7))
        here_pressure = (
            ad.world_map.room_pressure_for(ctx.room_id)
            if ad.world_map is not None and ctx.room_id and hasattr(ad.world_map, "room_pressure_for")
            else 0.0
        )
        if (
            scar_w >= 0.5
            and here_pressure >= 3.0
            and ad.world_map is not None
            and _can_afford_move(canonical)
            and (not ad.allowed or "MOVE" in ad.allowed)
        ):
            better = (
                ad.world_map.low_pressure_offered(
                    {"HARVEST"},
                    exclude=ctx.room_id,
                    near=ctx.room_id,
                    pressure_weight=scar_w,
                    max_pressure=here_pressure,
                )
                if hasattr(ad.world_map, "low_pressure_offered")
                else None
            )
            if better:
                move = route_to_room(ctx, better)
                if move is not None:
                    return PlaybookResult("FALLOW_ROTATION", move)
        ad.dwell = 0
        p = _proposal(vault, ad.default_args, ad.memory)
        if p is not None:
            p.arguments = {**(p.arguments or {}), "amount": _vault_harvest_amount(vault, canonical)}
        return PlaybookResult("TREASURY_HARVEST", p)
    return None
