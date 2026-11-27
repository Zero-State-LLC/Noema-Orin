"""m03 Rivet-Custodian declarative playbook: EQUIPMENT_AND_CRAFT -> SCAR_ATTEST -> ROLE_SUPPLY_AND_SPEND."""

from __future__ import annotations

from .common import PlaybookContext, PlaybookResult, step_equipment, step_scar_attest


def run_custodian_playbook(ctx: PlaybookContext) -> PlaybookResult | None:
    eq = step_equipment(ctx)
    if eq is not None:
        return eq
    att = step_scar_attest(ctx)
    if att is not None:
        return att
    return None
