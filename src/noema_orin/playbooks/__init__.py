"""Declarative per-role state-machine playbooks (T8/#162)."""

from __future__ import annotations

from typing import Callable

from .archivist import run_archivist_playbook
from .common import PlaybookContext, PlaybookResult, step_energy_and_recharge, step_supply_and_dwell_route
from .custodian import run_custodian_playbook
from .founder import run_founder_playbook
from .quartermaster import run_quartermaster_playbook
from .speaker import run_speaker_playbook
from .surveyor import run_surveyor_playbook

ROLE_PLAYBOOKS: dict[str, Callable[[PlaybookContext], PlaybookResult | None]] = {
    "founder": run_founder_playbook,
    "quartermaster": run_quartermaster_playbook,
    "custodian": run_custodian_playbook,
    "archivist": run_archivist_playbook,
    "speaker": run_speaker_playbook,
    "surveyor": run_surveyor_playbook,
}


def _infer_role(ctx: PlaybookContext) -> str:
    if ctx.role_name in ROLE_PLAYBOOKS:
        return ctx.role_name
    verbs = getattr(ctx.adapter, "verbs", set()) or set()
    if "ORG_CREATE" in verbs:
        return "founder"
    if "SUPPLY" in verbs:
        return "quartermaster"
    if "RECONSTRUCT" in verbs:
        return "archivist"
    if "MESSAGE" in verbs and "ORG_CREATE" not in verbs:
        return "speaker"
    if getattr(ctx.adapter, "explorer", False):
        return "surveyor"
    if getattr(ctx.adapter, "supply", None):
        return "custodian"
    return ""


def run_role_playbook(ctx: PlaybookContext) -> PlaybookResult | None:
    """Execute survival gate -> role state machine -> shared supply/build/agenda/dwell router."""
    energy = step_energy_and_recharge(ctx)
    if energy is not None:
        return energy
    role = _infer_role(ctx)
    runner = ROLE_PLAYBOOKS.get(role)
    if runner is not None:
        res = runner(ctx)
        if res is not None:
            return res
    return step_supply_and_dwell_route(ctx)


__all__ = ["PlaybookContext", "PlaybookResult", "ROLE_PLAYBOOKS", "run_role_playbook"]
