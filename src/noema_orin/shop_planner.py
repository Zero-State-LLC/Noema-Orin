"""Deterministic planner-only commerce, equipment, contract, and warden playbooks (RFC-0141 §2).

Pure functions over canonical observations and controller-local memory. None of these
economic or enforcement acts are exposed to the small LLM's index menu; bounded scarcity
formulas prevent hallucinated giveaway trades or unprovoked sanctions.
"""

from __future__ import annotations

from typing import Any

# Canonical 6-unit resident fleet loadouts (RFC-0141 §2.2).
ROLE_LOADOUTS: dict[str, tuple[str, ...]] = {
    "founder": ("signal_transceiver", "aegis_baffle"),
    "quartermaster": ("plasma_cutter", "cargo_rig"),
    "custodian": ("arc_welder", "cargo_rig"),
    "archivist": ("chrono_lens", "cipher_spike"),
    "speaker": ("signal_transceiver",),
    "surveyor": ("plasma_cutter", "arc_lance", "aegis_baffle"),
    "maintenance": (),
}

# Bounded scarcity pricing defaults (adjusted by RSI knob shop_margin_bias in [-1, 2]).
BASE_CELL_SELL_LOT_PRICE = 3
BASE_TOOL_SELL_LOT_PRICE = 5
BASE_ORE_BUY_ENERGY_PRICE = 6
BASE_CORE_SWAP_SILICA = 1


def _proposal(action: str, *, target_id: str | None = None, arguments: dict[str, Any] | None = None):
    """Build an ActionProposal if noema-client is available, else a plain dict for synthetic tests."""
    try:
        from noema_client.types import ActionProposal

        return ActionProposal(action=action, target_id=target_id, arguments=arguments or {})
    except ImportError:
        return {"action": action, "target_id": target_id, "arguments": arguments or {}}


def _room_has_ready_infra(canonical: dict[str, Any], infra_class: str, *, min_condition: int = 25) -> dict[str, Any] | None:
    loc = canonical.get("location") or {}
    for ent in loc.get("entities") or canonical.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        cls = str(ent.get("infra_type") or "").strip().lower()
        lbl = str(ent.get("label") or "").strip().lower().replace("-", "_")
        if cls != infra_class and infra_class not in lbl:
            continue
        if ent.get("in_progress") or ent.get("scar"):
            continue
        cond = ent.get("condition")
        if cond is not None and int(cond) < min_condition:
            continue
        return ent
    return None


def compute_shop_prices(margin_bias: int = 0) -> dict[str, int]:
    """Deterministic integer barter prices bounded by RSI shop_margin_bias (-1..2)."""
    bias = max(-1, min(2, int(margin_bias)))
    return {
        "power_cell_lot_price": max(2, min(6, BASE_CELL_SELL_LOT_PRICE + bias)),
        "tool_lot_price": max(3, min(8, BASE_TOOL_SELL_LOT_PRICE + bias)),
        "ore_buy_energy": max(4, min(8, BASE_ORE_BUY_ENERGY_PRICE - bias)),
        "core_swap_silica": max(1, min(2, BASE_CORE_SWAP_SILICA + (1 if bias >= 2 else 0))),
    }


def count_unequipped_broken_tools(canonical: dict[str, Any]) -> int:
    """Count broken (condition <= 0) unequipped tools/rigs/weapons carried by the agent."""
    inv = canonical.get("inventory") or []
    broken = 0
    for it in inv:
        if not isinstance(it, dict):
            continue
        if it.get("archetype") == "depleted_cell":
            continue
        if it.get("equipped_slot"):
            continue
        if int(it.get("condition") or 0) <= 0:
            broken += 1
    return broken


def plan_equipment_step(
    role: str,
    canonical: dict[str, Any],
    knobs: dict[str, Any] | None = None,
    allowed_actions: frozenset[str] | set[str] | None = None,
) -> Any | None:
    """Deterministic equipment upkeep: equip loadout, recycle depleted cells, repair worn tools, consume emergency cell."""
    if role == "maintenance":
        return None
    if allowed_actions is None:
        from .roles import role_for

        allowed_actions = frozenset(role_for(role)["allow"])
    knobs = knobs or {}
    repair_floor = max(10, min(50, int(knobs.get("tool_repair_floor", 25))))
    energy_floor = max(1, min(5, int(knobs.get("energy_reserve_floor", 2))))
    loadout = ROLE_LOADOUTS.get(role, ())
    inv = [it for it in (canonical.get("inventory") or []) if isinstance(it, dict)]
    eq = canonical.get("equipment") if isinstance(canonical.get("equipment"), dict) else {}
    res = canonical.get("resources") if isinstance(canonical.get("resources"), dict) else {}
    energy = int(res.get("energy") or 0)
    compute = int(res.get("compute") or 0)

    # 1. Auto-equip operational role loadout item if its slot is empty.
    if "EQUIP" in allowed_actions:
        for arch in loadout:
            for it in inv:
                if it.get("archetype") != arch or it.get("equipped_slot"):
                    continue
                slot = it.get("equip_slot")
                if int(it.get("condition") or 0) > 0 and slot and not eq.get(slot):
                    iid = str(it.get("item_id") or "")
                    if iid:
                        return _proposal("EQUIP", target_id=iid, arguments={"item_id": iid, "entity_id": iid})

    # 2. Emergency power_cell consumption when energy is at or below reserve floor.
    if "USE_ITEM" in allowed_actions and energy <= energy_floor:
        cell = next(
            (it for it in inv if it.get("archetype") == "power_cell" and int(it.get("condition") or 0) > 0 and it.get("item_id")),
            None,
        )
        if cell is not None:
            iid = str(cell["item_id"])
            return _proposal("USE_ITEM", target_id=iid, arguments={"item_id": iid, "entity_id": iid})

    # 3. Recycle depleted_cell at an operational generator (compute >= 1).
    if "RECHARGE" in allowed_actions and compute >= 1 and _room_has_ready_infra(canonical, "generator", min_condition=25):
        dep = next((it for it in inv if it.get("archetype") == "depleted_cell" and it.get("item_id")), None)
        if dep is not None:
            iid = str(dep["item_id"])
            return _proposal("RECHARGE", target_id=iid, arguments={"item_id": iid, "entity_id": iid})

    # 4. Repair worn or broken carried tool/weapon/rig at an operational workshop (only when role allows REPAIR).
    if "REPAIR" in allowed_actions and energy >= 2 and compute >= 1 and _room_has_ready_infra(canonical, "workshop", min_condition=25):
        worn = [
            it for it in inv
            if it.get("archetype") != "depleted_cell"
            and int(it.get("condition") or 0) <= repair_floor
            and int(it.get("condition") or 0) < int(it.get("max_condition") or 100)
            and it.get("item_id")
        ]
        if worn:
            worn.sort(key=lambda x: (int(x.get("condition") or 0), str(x.get("item_id"))))
            iid = str(worn[0]["item_id"])
            return _proposal("REPAIR", target_id=iid, arguments={"item_id": iid, "entity_id": iid})

    # 5. Custodian fabricates power_cell or missing loadout tools at a ready workshop when materials are on hand.
    if "CRAFT" in allowed_actions and role == "custodian" and energy >= 3 and compute >= 2 and _room_has_ready_infra(canonical, "workshop", min_condition=50):
        lots = canonical.get("material_lots") or []
        by_mat: dict[str, int] = {}
        for lot in lots:
            if isinstance(lot, dict) and lot.get("material"):
                by_mat[str(lot["material"]).upper()] = by_mat.get(str(lot["material"]).upper(), 0) + int(lot.get("amount") or 0)
        carried_arches = {str(it.get("archetype") or "") for it in inv}
        if "arc_welder" not in carried_arches and by_mat.get("FERROUS_ORE", 0) >= 3 and by_mat.get("SILICA_CELL", 0) >= 1:
            return _proposal("CRAFT", arguments={"recipe_id": "arc_welder"})
        battery_target = max(0, min(3, int(knobs.get("battery_reserve_target", 1))))
        cells_held = sum(1 for it in inv if it.get("archetype") == "power_cell")
        if cells_held < battery_target and by_mat.get("SILICA_CELL", 0) >= 2:
            return _proposal("CRAFT", arguments={"recipe_id": "power_cell"})

    return None


def _stall_energy_already_funded(
    stall: dict[str, Any],
    stall_id: str,
    needed_energy: int,
    recent_actions: list[dict[str, Any]] | None,
) -> bool:
    """True if observed stall escrow or an unconsumed recent energy stock already covers `needed_energy`."""
    stall_res = stall.get("resources")
    if isinstance(stall_res, dict) and int(stall_res.get("energy") or 0) >= needed_energy:
        return True
    for rec in reversed(recent_actions or []):
        if rec.get("action") != "TRADE" or rec.get("target") != stall_id:
            continue
        phase = str(rec.get("phase") or "").lower()
        if phase == "list":
            return False
        if phase == "stock":
            return True
    return False


def plan_quartermaster_shop(
    canonical: dict[str, Any],
    knobs: dict[str, Any] | None = None,
    recent_actions: list[dict[str, Any]] | None = None,
) -> Any | None:
    """Deterministic m02 Tallow-Quartermaster storefront stocking & listing planner (RFC-0141 §2.2)."""
    stall = _room_has_ready_infra(canonical, "barter_stall", min_condition=25)
    if stall is None:
        return None
    stall_id = str(stall.get("entity_id") or "")
    if not stall_id:
        return None
    knobs = knobs or {}
    prices = compute_shop_prices(int(knobs.get("shop_margin_bias", 0)))
    battery_reserve = max(0, min(3, int(knobs.get("battery_reserve_target", 1))))
    res = canonical.get("resources") if isinstance(canonical.get("resources"), dict) else {}
    energy = int(res.get("energy") or 0)
    compute = int(res.get("compute") or 0)
    if compute < 1:
        return None

    inv = [it for it in (canonical.get("inventory") or []) if isinstance(it, dict)]
    listings = [
        l for l in (canonical.get("shop_listings") or [])
        if isinstance(l, dict) and l.get("stall_id") == stall_id and int(l.get("fills_remaining") or 0) > 0
    ]
    open_kinds = {str(l.get("listing_kind") or "") for l in listings}

    # 1. Stock surplus fresh power_cells beyond personal battery_reserve_target into the barter_stall.
    surplus_cells = [
        it for it in inv
        if it.get("archetype") == "power_cell" and not it.get("equipped_slot") and int(it.get("condition") or 0) > 0 and it.get("item_id")
    ]
    if len(surplus_cells) > battery_reserve:
        iid = str(surplus_cells[0]["item_id"])
        return _proposal(
            "TRADE",
            target_id=stall_id,
            arguments={
                "phase": "stock",
                "stall_id": stall_id,
                "asset": {"kind": "ITEM", "item_id": iid},
            },
        )

    # 2. Ensure a BUY_ORDER exists: fund energy once, then immediately publish the BUY_ORDER on the next turn.
    if len(listings) < 3 and "BUY_ORDER" not in open_kinds:
        funded = _stall_energy_already_funded(stall, stall_id, prices["ore_buy_energy"], recent_actions)
        if funded:
            return _proposal(
                "TRADE",
                target_id=stall_id,
                arguments={
                    "phase": "list",
                    "stall_id": stall_id,
                    "listing_kind": "BUY_ORDER",
                    "offer_asset": {"kind": "RESOURCE", "resource": "energy", "amount": prices["ore_buy_energy"]},
                    "ask_asset": {"kind": "LOT", "material": "FERROUS_ORE", "amount": 3},
                    "max_fills": 1,
                },
            )
        if energy >= prices["ore_buy_energy"] + 8:
            return _proposal(
                "TRADE",
                target_id=stall_id,
                arguments={
                    "phase": "stock",
                    "stall_id": stall_id,
                    "asset": {"kind": "RESOURCE", "resource": "energy", "amount": prices["ore_buy_energy"]},
                },
            )

    return None


def plan_warden_defense_and_sanction(
    role: str,
    canonical: dict[str, Any],
    options: list[dict[str, Any]],
    cohort_ids: set[str] | None = None,
) -> Any | None:
    """Deterministic defensive warden (m06) and forensic archivist (m04) enforcement (RFC-0141 §2.2 & RFC-0143)."""
    if role not in ("surveyor", "archivist"):
        return None
    res = canonical.get("resources") if isinstance(canonical.get("resources"), dict) else {}
    compute = int(res.get("compute") or 0)
    energy = int(res.get("energy") or 0)
    me = str(canonical.get("self") or "")
    cohort = cohort_ids or set()

    # 1. Archivist prioritizes forensic INVESTIGATE on public crime residues.
    if role == "archivist":
        inv_opt = next((o for o in options if o.get("action") == "INVESTIGATE"), None)
        if inv_opt is not None:
            raw = inv_opt.get("raw") or {}
            rid = str(raw.get("residue_id") or inv_opt.get("target_id") or "")
            return _proposal("INVESTIGATE", target_id=rid or None, arguments={"residue_id": rid} if rid else {})

    # 2. Defensive CONTEST_DEFEND when an open contest targets a cohort member or Compact asset (NEVER CONTEST_DECLARE).
    if compute >= 2 and energy >= 4:
        for c in canonical.get("contests") or []:
            if not isinstance(c, dict) or c.get("status") != "OPEN":
                continue
            cid = str(c.get("contest_id") or "")
            if not cid or c.get("declarer_id") == me or c.get("defender_id") == me:
                continue
            target = c.get("target") if isinstance(c.get("target"), dict) else {}
            tgt_holder = str(target.get("holder_id") or target.get("agent_id") or "")
            if tgt_holder in cohort or c.get("contest_form") in ("INFRASTRUCTURE_DISRUPTION", "RESOURCE_SEIZURE"):
                return _proposal(
                    "CONTEST_DEFEND",
                    target_id=cid,
                    arguments={"contest_id": cid, "stake": {"energy": 2, "compute": 1}},
                )

    # 3. Evidence-backed SANCTION (planner-only) for surveyor warden when an explicit detection_id is advertised.
    if role == "surveyor":
        sanc_opt = next((o for o in options if o.get("action") == "SANCTION"), None)
        if sanc_opt is not None:
            raw = sanc_opt.get("raw") or {}
            det_id = str(raw.get("detection_id") or sanc_opt.get("target_id") or "")
            if det_id:
                return _proposal("SANCTION", target_id=det_id, arguments={"detection_id": det_id})

    return None


def plan_civic_contract(
    role: str,
    canonical: dict[str, Any],
    home_org_id: str | None,
) -> Any | None:
    """Deterministic m01 Aphelia-Founder civic contract issuer (1..2 open WS06 contracts at Civic Exchange)."""
    if role != "founder" or not home_org_id:
        return None
    loc = canonical.get("location") or {}
    if loc.get("room_id") != "room.civic-exchange":
        return None
    res = canonical.get("resources") if isinstance(canonical.get("resources"), dict) else {}
    if int(res.get("compute") or 0) < 1:
        return None
    open_here = [
        c for c in (canonical.get("open_contracts") or [])
        if isinstance(c, dict) and c.get("org_id") == home_org_id
    ]
    if len(open_here) >= 2:
        return None
    # Check org treasury has >= 6 energy to escrow a DELIVER_LOT contract cleanly.
    org = next(
        (o for o in (canonical.get("organizations") or []) if isinstance(o, dict) and o.get("org_id") == home_org_id),
        None,
    )
    treasury = (org or {}).get("treasury") if isinstance((org or {}).get("treasury"), dict) else {}
    if int(treasury.get("energy") or 0) >= 6 and not any(c.get("kind") == "DELIVER_LOT" for c in open_here):
        return _proposal(
            "CONTRACT_POST",
            target_id=home_org_id,
            arguments={
                "org_id": home_org_id,
                "contract_kind": "DELIVER_LOT",
                "target_material": "FERROUS_ORE",
                "target_count": 2,
                "reward_resource": "energy",
                "reward_amount": 6,
            },
        )
    return None
