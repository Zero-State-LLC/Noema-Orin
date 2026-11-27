"""m06 Perigee-Surveyor declarative playbook: WARDEN_DEFENSE -> EQUIPMENT -> SCAR_ATTEST."""

from __future__ import annotations

from ..shop_planner import plan_warden_defense_and_sanction
from .common import PlaybookContext, PlaybookResult, step_equipment, step_scar_attest


def run_surveyor_playbook(ctx: PlaybookContext) -> PlaybookResult | None:
    ad = ctx.adapter
    warden_prop = plan_warden_defense_and_sanction("surveyor", ctx.canonical, ctx.options, getattr(ad, "cohort_ids", None))
    if warden_prop is not None and hasattr(warden_prop, "action"):
        ad.dwell = 0
        return PlaybookResult("WARDEN_DEFENSE", warden_prop)
    eq = step_equipment(ctx)
    if eq is not None:
        return eq
    att = step_scar_attest(ctx)
    if att is not None:
        return att
    return None
