"""m05 Cantor-Speaker declarative playbook: EQUIPMENT -> PUBLISH_NOTICE -> BOARD_DIGEST -> HERALD_PATROL -> SCAR_ATTEST."""

from __future__ import annotations

from .common import PlaybookContext, PlaybookResult, route_to_room, step_equipment, step_scar_attest


def run_speaker_playbook(ctx: PlaybookContext) -> PlaybookResult | None:
    from noema_client.types import ActionProposal

    from ..orin_adapter import _proposal, grounded_market_and_contract_digest

    ad = ctx.adapter
    canonical = ctx.canonical
    options = ctx.options

    eq = step_equipment(ctx)
    if eq is not None:
        return eq

    notice = next(
        (
            o for o in options
            if o["action"] == "ORG_OFFICE_ACT"
            and str((o.get("raw") or {}).get("authority_profile") or "PUBLISH_NOTICE") == "PUBLISH_NOTICE"
        ),
        None,
    )
    if notice is not None and "MESSAGE" in ad.verbs and "ORG_CREATE" not in ad.verbs:
        p = _proposal(notice, ad.default_args, ad.memory, world_map=ad.world_map, canonical=canonical)
        if p is not None:
            ad.dwell = 0
            return PlaybookResult("PUBLISH_NOTICE", p)

    if ad._social_outreach_ready():
        board_opt = next((o for o in options if o["action"] == "BOARD"), None)
        if board_opt is not None and ad.world_map is not None:
            digest_txt = grounded_market_and_contract_digest(ad.memory, ad.world_map, canonical, org_name="Reach Compact")
            if digest_txt:
                ad.dwell = 0
                return PlaybookResult(
                    "BOARD_DIGEST",
                    ActionProposal(action="BOARD", target_id=board_opt.get("target_id"), arguments={"text": digest_txt}),
                )
        if (
            ad.world_map is not None
            and ctx.room_id
            and ctx.room_id != "room.civic-exchange"
            and not ad.world_map.observed_listings(room_id="room.civic-exchange")
        ):
            move = route_to_room(ctx, "room.civic-exchange")
            if move is not None:
                return PlaybookResult("HERALD_REFRESH_EXCHANGE", move)

    att = step_scar_attest(ctx)
    if att is not None:
        return att
    return None
