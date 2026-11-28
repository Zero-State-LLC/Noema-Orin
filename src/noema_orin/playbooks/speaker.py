"""m05 Cantor-Speaker declarative playbook: EQUIPMENT -> PUBLISH_NOTICE -> BOARD_DIGEST -> HERALD_PATROL -> SCAR_ATTEST."""

from __future__ import annotations

from .common import PlaybookContext, PlaybookResult, route_to_room, step_equipment, step_scar_attest


def run_speaker_playbook(ctx: PlaybookContext) -> PlaybookResult | None:
    from noema_client.types import ActionProposal

    from ..orin_adapter import _proposal, grounded_market_and_contract_digest
    from ..planner import home_org
    from ..shop_planner import storefront_room

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
        # D-093: the engine keeps one notice per room and drops it after a cycle; a second post in the same room
        # and cycle only overwrites the first (34 of m05's 130 notices).
        slot = (ctx.room_id, canonical.get("cycle"))
        fresh = slot[1] is None or getattr(ad, "_notice_slot", None) != slot
        p = _proposal(notice, ad.default_args, ad.memory, world_map=ad.world_map, canonical=canonical) if fresh else None
        if p is not None:
            ad.dwell = 0
            ad._notice_slot = slot
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
        shop = storefront_room(ad.world_map, home_org(canonical))
        if (
            ad.world_map is not None
            and ctx.room_id
            and ctx.room_id != shop
            and not ad.world_map.observed_listings(room_id=shop)
        ):
            move = route_to_room(ctx, shop)
            if move is not None:
                return PlaybookResult("HERALD_REFRESH_EXCHANGE", move)

    att = step_scar_attest(ctx)
    if att is not None:
        return att
    return None
