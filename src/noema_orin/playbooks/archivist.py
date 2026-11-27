"""m04 Vellum-Archivist declarative playbook: FORENSICS -> EQUIPMENT -> FOSSIL_COMMEMORATE -> ATTENTION -> EVIDENCE_INSPECT."""

from __future__ import annotations

from ..shop_planner import plan_warden_defense_and_sanction
from .common import PlaybookContext, PlaybookResult, step_equipment


def run_archivist_playbook(ctx: PlaybookContext) -> PlaybookResult | None:
    from noema_client.types import ActionProposal

    from ..orin_adapter import _proposal
    from ..planner import has_role_verb

    ad = ctx.adapter
    canonical = ctx.canonical
    options = ctx.options

    warden_prop = plan_warden_defense_and_sanction("archivist", canonical, options, getattr(ad, "cohort_ids", None))
    if warden_prop is not None and hasattr(warden_prop, "action"):
        ad.dwell = 0
        return PlaybookResult("WARDEN_FORENSICS", warden_prop)

    eq = step_equipment(ctx)
    if eq is not None:
        return eq

    if any(o["action"] == "COMMEMORATE" for o in options):
        commemorated = (
            {str(r[0]) for r in ad.memory.db.execute("SELECT text FROM facts WHERE kind='commemorated'").fetchall()}
            if ad.memory is not None
            else set()
        )
        for scar in canonical.get("scars") or []:
            if not isinstance(scar, dict) or not scar.get("scar_id"):
                continue
            sid = str(scar["scar_id"])
            if (scar.get("fossilized") or float(scar.get("strength") or 0.0) >= 0.85) and sid not in commemorated:
                if ad.memory is not None:
                    ad.memory.remember(sid, kind="commemorated", room=ctx.room_id, sequence=ctx.seq)
                ad.dwell = 0
                return PlaybookResult(
                    "COMMEMORATE_FOSSIL",
                    ActionProposal(action="COMMEMORATE", target_id=sid, arguments={"scar_id": sid, "target_id": sid}),
                )

    att = (canonical.get("resources") or {}).get("attention")
    if isinstance(att, (int, float)) and att < 2:
        ad.dwell = 0
        return PlaybookResult("WAIT_ATTENTION", ActionProposal(action="WAIT"))

    if isinstance(att, (int, float)) and att >= 4 and not has_role_verb(options, ad.verbs):
        seen = {r.get("target") for r in ad.recent[-ad._inspect_novelty_window():] if r["action"] == "INSPECT"}
        seen |= ad._published_subjects()
        insp = next((o for o in options if o["action"] == "INSPECT" and o.get("target_id") not in seen), None)
        if insp is not None:
            ad.dwell = 0
            return PlaybookResult("EVIDENCE_INSPECT", _proposal(insp, ad.default_args, ad.memory))
    return None
