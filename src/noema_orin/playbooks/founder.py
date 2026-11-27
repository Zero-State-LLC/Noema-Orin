"""m01 Aphelia-Founder declarative playbook: WELCOME -> GOVERNANCE -> CONTRACTS -> EXCHANGE."""

from __future__ import annotations

from ..planner import home_org
from ..shop_planner import (
    founder_needs_exchange_visit,
    plan_civic_contract,
    plan_founder_governance_and_commemorate,
)
from .common import PlaybookContext, PlaybookResult, route_to_room, step_equipment


def run_founder_playbook(ctx: PlaybookContext) -> PlaybookResult | None:
    ad = ctx.adapter
    welcome = ad._welcome(ctx.canonical, ctx.options) if "ORG_CREATE" in ad.verbs else None
    if welcome is not None:
        return PlaybookResult("WELCOME_NEWCOMER", welcome)
    eq = step_equipment(ctx)
    if eq is not None:
        return eq
    home_id = home_org(ctx.canonical)
    gov_prop = plan_founder_governance_and_commemorate(ctx.canonical, home_id, ad.memory, ctx.options)
    if gov_prop is not None and hasattr(gov_prop, "action"):
        ad.dwell = 0
        return PlaybookResult("GOVERNANCE_OR_COMMEMORATE", gov_prop)
    contract_prop = plan_civic_contract("founder", ctx.canonical, home_id, world_map=ad.world_map)
    if contract_prop is not None and hasattr(contract_prop, "action"):
        ad.dwell = 0
        return PlaybookResult("CIVIC_CONTRACT", contract_prop)
    if founder_needs_exchange_visit(ctx.canonical, home_id, ad.world_map):
        move = route_to_room(ctx, "room.civic-exchange")
        if move is not None:
            return PlaybookResult("RETURN_EXCHANGE", move)
    return None
