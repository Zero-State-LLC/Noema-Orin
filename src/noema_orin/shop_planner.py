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


# Material requirements for fleet crafting recipes (RFC-0139 / RFC-0141 §2.2).
CRAFT_RECIPE_COSTS: dict[str, dict[str, int]] = {
    "power_cell": {"SILICA_CELL": 2},
    "arc_welder": {"FERROUS_ORE": 3, "SILICA_CELL": 1},
    "plasma_cutter": {"FERROUS_ORE": 3, "SILICA_CELL": 1},
    "chrono_lens": {"SILICA_CELL": 2, "SALVAGE_COMPOSITE": 1},
    "signal_transceiver": {"SILICA_CELL": 2, "FERROUS_ORE": 1},
    "cargo_rig": {"FERROUS_ORE": 2, "SALVAGE_COMPOSITE": 2},
    "aegis_baffle": {"FERROUS_ORE": 2, "SALVAGE_COMPOSITE": 2},
    "cipher_spike": {"SILICA_CELL": 2, "SALVAGE_COMPOSITE": 2},
    "arc_lance": {"FERROUS_ORE": 3, "SILICA_CELL": 2},
}


def _can_craft_recipe(recipe_id: str, by_mat: dict[str, int]) -> bool:
    req = CRAFT_RECIPE_COSTS.get(recipe_id)
    if not req:
        return False
    return all(by_mat.get(mat, 0) >= amt for mat, amt in req.items())


def plan_equipment_step(
    role: str,
    canonical: dict[str, Any],
    knobs: dict[str, Any] | None = None,
    allowed_actions: frozenset[str] | set[str] | None = None,
    world_map=None,
) -> Any | None:
    """Deterministic equipment upkeep, contract fulfillment, and fleet-aware crafting (RFC-0141 §2.2, T6/#160)."""
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
    loc = canonical.get("location") or {}
    room_id = str(loc.get("room_id") or "")
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

    # 4b. Custodian fulfills co-located open CRAFT_ITEM or completed REPAIR_TARGET contracts (RFC-0144 §4).
    if "CONTRACT_FULFILL" in allowed_actions and role == "custodian" and room_id:
        me = str(canonical.get("self") or "")
        room_ents = {
            str(e.get("entity_id")): e
            for e in (loc.get("entities") or canonical.get("entities") or [])
            if isinstance(e, dict) and e.get("entity_id")
        }
        for c in canonical.get("open_contracts") or []:
            if not isinstance(c, dict) or str(c.get("status") or "OPEN") != "OPEN":
                continue
            if c.get("room_id") != room_id or (me and c.get("poster_id") == me):
                continue
            cid = str(c.get("contract_id") or "")
            if not cid:
                continue
            kind = str(c.get("kind") or "")
            if kind == "CRAFT_ITEM":
                arch = str(c.get("target_item_archetype") or "")
                qualifying = next(
                    (
                        it for it in inv
                        if it.get("archetype") == arch
                        and not it.get("equipped_slot")
                        and int(it.get("condition") or 0) >= 80
                    ),
                    None,
                )
                if qualifying is not None:
                    return _proposal("CONTRACT_FULFILL", target_id=cid, arguments={"contract_id": cid})
            elif kind == "REPAIR_TARGET":
                tid = str(c.get("target_entity_id") or "")
                tgt = room_ents.get(tid)
                tcond = int(c.get("target_condition") or 80)
                if tgt is not None and int(tgt.get("condition") or 0) >= tcond:
                    return _proposal("CONTRACT_FULFILL", target_id=cid, arguments={"contract_id": cid})

    # 5. Custodian fabricates self loadout, power_cells, open CRAFT_ITEM contracts, or missing cohort loadouts.
    if "CRAFT" in allowed_actions and role == "custodian" and energy >= 3 and compute >= 2 and _room_has_ready_infra(canonical, "workshop", min_condition=50):
        lots = canonical.get("material_lots") or []
        by_mat: dict[str, int] = {}
        for lot in lots:
            if isinstance(lot, dict) and lot.get("material"):
                by_mat[str(lot["material"]).upper()] = by_mat.get(str(lot["material"]).upper(), 0) + int(lot.get("amount") or 0)
        carried_arches = {str(it.get("archetype") or "") for it in inv}
        if "arc_welder" not in carried_arches and _can_craft_recipe("arc_welder", by_mat):
            return _proposal("CRAFT", arguments={"recipe_id": "arc_welder"})
        battery_target = max(0, min(3, int(knobs.get("battery_reserve_target", 1))))
        cells_held = sum(1 for it in inv if it.get("archetype") == "power_cell")
        if cells_held < battery_target and _can_craft_recipe("power_cell", by_mat):
            return _proposal("CRAFT", arguments={"recipe_id": "power_cell"})
        # Open CRAFT_ITEM contract targets (RFC-0144 §4)
        for c in canonical.get("open_contracts") or []:
            if not isinstance(c, dict) or str(c.get("status") or "OPEN") != "OPEN" or c.get("kind") != "CRAFT_ITEM":
                continue
            arch = str(c.get("target_item_archetype") or "")
            has_spare = any(
                it.get("archetype") == arch and not it.get("equipped_slot") and int(it.get("condition") or 0) >= 80
                for it in inv
            )
            if arch and not has_spare and _can_craft_recipe(arch, by_mat):
                return _proposal("CRAFT", arguments={"recipe_id": arch})
        # Fleet-aware crafting from shared/map.db observed_equipment() & observed_listings()
        if world_map is not None:
            needed_arch = _missing_cohort_archetype(world_map)
            if needed_arch:
                has_spare = any(
                    it.get("archetype") == needed_arch and not it.get("equipped_slot") and int(it.get("condition") or 0) >= 80
                    for it in inv
                )
                if not has_spare and _can_craft_recipe(needed_arch, by_mat):
                    return _proposal("CRAFT", arguments={"recipe_id": needed_arch})

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


def _stall_stocked_items(stall: dict[str, Any]) -> list[dict[str, Any]]:
    raw = stall.get("inventory") or stall.get("stocked_items") or stall.get("items") or []
    return [it for it in raw if isinstance(it, dict) and it.get("item_id")]


def _committed_listing_item_ids(listings: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for l in listings:
        offer = l.get("offer_asset") if isinstance(l.get("offer_asset"), dict) else {}
        if offer.get("kind") == "ITEM" and offer.get("item_id"):
            out.add(str(offer["item_id"]))
    return out


def _open_buy_materials(listings: list[dict[str, Any]]) -> set[str]:
    mats: set[str] = set()
    for l in listings:
        if str(l.get("listing_kind") or "") != "BUY_ORDER":
            continue
        ask = l.get("ask_asset") if isinstance(l.get("ask_asset"), dict) else {}
        if ask.get("kind") == "LOT" and ask.get("material"):
            mats.add(str(ask["material"]).upper())
    return mats


def quartermaster_needs_shop_visit(
    canonical: dict[str, Any],
    world_map,
    knobs: dict[str, Any] | None = None,
) -> bool:
    """True when m02 is outside civic-exchange with surplus stock or missing storefront listings (T4/#158)."""
    loc = canonical.get("location") or {}
    if loc.get("room_id") == "room.civic-exchange":
        return False
    knobs = knobs or {}
    battery_reserve = max(0, min(3, int(knobs.get("battery_reserve_target", 1))))
    qm_loadout = set(ROLE_LOADOUTS.get("quartermaster", ()))
    inv = [it for it in (canonical.get("inventory") or []) if isinstance(it, dict)]
    surplus_cells = [
        it for it in inv
        if it.get("archetype") == "power_cell" and not it.get("equipped_slot") and int(it.get("condition") or 0) > 0
    ]
    if len(surplus_cells) > battery_reserve:
        return True
    surplus_tools = [
        it for it in inv
        if not it.get("equipped_slot")
        and str(it.get("archetype") or "") not in ({"", "power_cell", "depleted_cell"} | qm_loadout)
        and int(it.get("condition") or 0) >= 50
    ]
    if surplus_tools:
        return True
    if world_map is not None and hasattr(world_map, "observed_listings"):
        listings = [
            l for l in world_map.observed_listings(room_id="room.civic-exchange")
            if int(l.get("fills_remaining") or 0) > 0
        ]
        if not listings:
            return True
    return False


def plan_quartermaster_shop(
    canonical: dict[str, Any],
    knobs: dict[str, Any] | None = None,
    recent_actions: list[dict[str, Any]] | None = None,
) -> Any | None:
    """Deterministic m02 Tallow-Quartermaster storefront stocking & listing planner (RFC-0141 §2.2, T4/#158)."""
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
    qm_loadout = set(ROLE_LOADOUTS.get("quartermaster", ()))

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

    # 2. Stock unequipped non-loadout SOUND+ tools/rigs into the barter_stall for SELL_OFFER.
    surplus_tools = [
        it for it in inv
        if not it.get("equipped_slot")
        and it.get("item_id")
        and str(it.get("archetype") or "") not in ({"", "power_cell", "depleted_cell"} | qm_loadout)
        and int(it.get("condition") or 0) >= 50
    ]
    if surplus_tools:
        iid = str(surplus_tools[0]["item_id"])
        return _proposal(
            "TRADE",
            target_id=stall_id,
            arguments={
                "phase": "stock",
                "stall_id": stall_id,
                "asset": {"kind": "ITEM", "item_id": iid},
            },
        )

    # 3. Publish CORE_SWAP and SELL_OFFER listings for uncommitted items already escrowed in the stall.
    stocked = _stall_stocked_items(stall)
    committed_ids = _committed_listing_item_ids(listings)
    free_stocked = [it for it in stocked if str(it["item_id"]) not in committed_ids and int(it.get("condition") or 0) >= 50]
    if len(listings) < 4 and free_stocked:
        free_cells = [it for it in free_stocked if it.get("archetype") == "power_cell"]
        free_tools = [it for it in free_stocked if it.get("archetype") not in ("power_cell", "depleted_cell")]
        if free_cells and "CORE_SWAP" not in open_kinds:
            cid = str(free_cells[0]["item_id"])
            return _proposal(
                "TRADE",
                target_id=stall_id,
                arguments={
                    "phase": "list",
                    "stall_id": stall_id,
                    "listing_kind": "CORE_SWAP",
                    "offer_asset": {
                        "kind": "ITEM",
                        "item_id": cid,
                        "predicate": {"archetype": "power_cell", "min_condition": 80},
                        "count": 1,
                    },
                    "ask_asset": {
                        "kind": "ITEM",
                        "predicate": {"archetype": "depleted_cell"},
                        "count": 1,
                    },
                    "max_fills": 1,
                },
            )
        if free_cells:
            cid = str(free_cells[0]["item_id"])
            return _proposal(
                "TRADE",
                target_id=stall_id,
                arguments={
                    "phase": "list",
                    "stall_id": stall_id,
                    "listing_kind": "SELL_OFFER",
                    "offer_asset": {
                        "kind": "ITEM",
                        "item_id": cid,
                        "predicate": {"archetype": "power_cell", "min_condition": 80},
                        "count": 1,
                    },
                    "ask_asset": {"kind": "LOT", "material": "FERROUS_ORE", "amount": prices["power_cell_lot_price"]},
                    "max_fills": 1,
                },
            )
        if free_tools:
            tid = str(free_tools[0]["item_id"])
            tarch = str(free_tools[0].get("archetype") or "")
            offer_asset: dict[str, Any] = {"kind": "ITEM", "item_id": tid, "count": 1}
            if tarch:
                offer_asset["predicate"] = {"archetype": tarch, "min_condition": 50}
            return _proposal(
                "TRADE",
                target_id=stall_id,
                arguments={
                    "phase": "list",
                    "stall_id": stall_id,
                    "listing_kind": "SELL_OFFER",
                    "offer_asset": offer_asset,
                    "ask_asset": {"kind": "LOT", "material": "FERROUS_ORE", "amount": prices["tool_lot_price"]},
                    "max_fills": 1,
                },
            )

    # 4. Ensure BUY_ORDERs exist (FERROUS_ORE first, then SALVAGE_COMPOSITE): fund energy once, then list.
    open_buy_mats = _open_buy_materials(listings)
    wanted_mat = next((m for m in ("FERROUS_ORE", "SALVAGE_COMPOSITE") if m not in open_buy_mats), None)
    if len(listings) < 4 and wanted_mat is not None:
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
                    "ask_asset": {"kind": "LOT", "material": wanted_mat, "amount": 3},
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


def _missing_cohort_archetype(world_map) -> str | None:
    """Identify the first missing ROLE_LOADOUTS archetype across known cohort members in shared/map.db."""
    if world_map is None or not hasattr(world_map, "observed_equipment"):
        return None
    equip_rows = world_map.observed_equipment()
    by_player: dict[str, set[str]] = {}
    for row in equip_rows:
        if int(row.get("condition") or 0) > 0:
            by_player.setdefault(str(row["player_id"]), set()).add(str(row.get("archetype") or ""))
    # Also include positioned cohort members who currently have zero recorded items.
    pos_players: list[str] = []
    if hasattr(world_map, "db"):
        pos_players = [str(r[0]) for r in world_map.db.execute("SELECT player_id FROM positions").fetchall() if r[0]]
    all_players = sorted(set(by_player) | set(pos_players))
    for pid in all_players:
        low = pid.lower()
        for role, loadout in ROLE_LOADOUTS.items():
            if role == "maintenance" or not loadout:
                continue
            if role in low:
                held = by_player.get(pid, set())
                for arch in loadout:
                    if arch not in held:
                        return arch
    if hasattr(world_map, "observed_listings"):
        ex_listings = [
            l for l in world_map.observed_listings(room_id="room.civic-exchange")
            if int(l.get("fills_remaining") or 0) > 0 and "power_cell" in str(l.get("offer_json") or "")
        ]
        if not ex_listings:
            return "power_cell"
    return None


def founder_needs_exchange_visit(
    canonical: dict[str, Any],
    home_org_id: str | None,
    world_map=None,
) -> bool:
    """True when m01 is outside Civic Exchange and should return to replenish civic contracts (T5/#159)."""
    if not home_org_id:
        return False
    loc = canonical.get("location") or {}
    if loc.get("room_id") == "room.civic-exchange":
        return False
    open_org = [
        c for c in (canonical.get("open_contracts") or [])
        if isinstance(c, dict) and c.get("org_id") == home_org_id
    ]
    if len(open_org) >= 2:
        return False
    org = next(
        (o for o in (canonical.get("organizations") or []) if isinstance(o, dict) and o.get("org_id") == home_org_id),
        None,
    )
    treasury = (org or {}).get("treasury") if isinstance((org or {}).get("treasury"), dict) else {}
    return int(treasury.get("energy") or 0) >= 6 or int(treasury.get("storage") or 0) >= 4


def plan_founder_governance_and_commemorate(
    canonical: dict[str, Any],
    home_org_id: str | None,
    memory,
    options: list[dict[str, Any]],
) -> Any | None:
    """Deterministic 1-shot OPEN_CHARTER governance rule and crystallized lore COMMEMORATE for m01 (T5/#159)."""
    if not home_org_id:
        return None
    res = canonical.get("resources") if isinstance(canonical.get("resources"), dict) else {}
    seq = canonical.get("sequence")
    # 1. Publish OPEN_CHARTER governance rule once when org has an occupied office and no published open charter.
    org = next(
        (o for o in (canonical.get("organizations") or []) if isinstance(o, dict) and o.get("org_id") == home_org_id),
        None,
    )
    gov = (org or {}).get("governance_rule") if isinstance((org or {}).get("governance_rule"), dict) else {}
    already_open = bool(gov.get("published") and str(gov.get("admission_mode") or "").upper() == "OPEN_CHARTER")
    mem_done = False
    if memory is not None:
        mem_done = bool(
            memory.db.execute(
                "SELECT 1 FROM facts WHERE kind='governance_rule' AND text=?", (f"open_charter:{home_org_id}",)
            ).fetchone()
        )
    if not already_open and not mem_done and any(o.get("action") == "ORG_GOVERNANCE_RULE" for o in options):
        offices = [
            str(off.get("office_id"))
            for off in ((org or {}).get("offices") or [])
            if isinstance(off, dict) and off.get("office_id") and off.get("status") != "RETIRED"
        ]
        if offices:
            if memory is not None:
                memory.remember(f"open_charter:{home_org_id}", kind="governance_rule", room=None, sequence=seq)
            return _proposal(
                "ORG_GOVERNANCE_RULE",
                target_id=home_org_id,
                arguments={
                    "org_id": home_org_id,
                    "rule": {
                        "decision": {"offices": offices[:1], "quorum": 1},
                        "appointment": {"mechanism": "OFFICE_APPOINTED"},
                        "jurisdiction": {"rooms": ["room.civic-exchange"], "objects": [], "members": []},
                        "enforcement": {"operation": "PUBLISH_NOTICE"},
                        "failure": {"on_vacancy": "SUCCEED_THEN_DECIDE", "on_deadlock": "REFUSE"},
                        "evidence": {"record": "PUBLIC_NOTICE"},
                        "admission_mode": "OPEN_CHARTER",
                    },
                },
            )

    # 2. COMMEMORATE crystallized lore attractors in the current room, once per attractor.
    if int(res.get("compute") or 0) >= 1 and any(o.get("action") == "COMMEMORATE" for o in options):
        commemorated: set[str] = set()
        if memory is not None:
            commemorated = {
                str(r[0]) for r in memory.db.execute("SELECT text FROM facts WHERE kind='commemorated'").fetchall()
            }
        for lore in canonical.get("lore_attractors") or []:
            if not isinstance(lore, dict):
                continue
            aid = str(lore.get("attractor_id") or "")
            if not aid or str(lore.get("basin") or "").lower() != "crystallized" or aid in commemorated:
                continue
            if memory is not None:
                memory.remember(aid, kind="commemorated", room=(canonical.get("location") or {}).get("room_id"), sequence=seq)
            return _proposal("COMMEMORATE", target_id=aid, arguments={"attractor_id": aid, "target_id": aid})
    return None


def plan_civic_contract(
    role: str,
    canonical: dict[str, Any],
    home_org_id: str | None,
    world_map=None,
) -> Any | None:
    """Deterministic m01 Aphelia-Founder civic contract issuer (1..2 open WS06 contracts across 4 kinds, T5/#159)."""
    if role != "founder" or not home_org_id:
        return None
    loc = canonical.get("location") or {}
    room_id = str(loc.get("room_id") or "")
    res = canonical.get("resources") if isinstance(canonical.get("resources"), dict) else {}
    if int(res.get("compute") or 0) < 1:
        return None
    open_here = [
        c for c in (canonical.get("open_contracts") or [])
        if isinstance(c, dict) and c.get("org_id") == home_org_id
    ]
    if len(open_here) >= 2:
        return None
    open_kinds = {str(c.get("kind") or "") for c in open_here}
    org = next(
        (o for o in (canonical.get("organizations") or []) if isinstance(o, dict) and o.get("org_id") == home_org_id),
        None,
    )
    treasury = (org or {}).get("treasury") if isinstance((org or {}).get("treasury"), dict) else {}
    t_energy = int(treasury.get("energy") or 0)
    t_storage = int(treasury.get("storage") or 0)

    # 1. REPAIR_TARGET in any room with damaged public infrastructure (contract binds to current room_id).
    if "REPAIR_TARGET" not in open_kinds and t_storage >= 3:
        damaged = [
            e for e in (loc.get("entities") or canonical.get("entities") or [])
            if isinstance(e, dict)
            and (str(e.get("entity_type") or "").upper() == "INFRASTRUCTURE" or bool(e.get("infra_type")))
            and not e.get("in_progress")
            and e.get("entity_id")
            and e.get("condition") is not None
            and int(e.get("condition")) < 80
        ]
        if damaged:
            damaged.sort(key=lambda x: (int(x.get("condition") or 0), str(x.get("entity_id"))))
            eid = str(damaged[0]["entity_id"])
            return _proposal(
                "CONTRACT_POST",
                target_id=home_org_id,
                arguments={
                    "org_id": home_org_id,
                    "contract_kind": "REPAIR_TARGET",
                    "entity_id": eid,
                    "target_condition": 80,
                    "reward_resource": "storage",
                    "reward_amount": 3,
                },
            )

    # 2. ATTEST_ROOM in any room carrying an active scar.
    if "ATTEST_ROOM" not in open_kinds and t_storage >= 2 and (canonical.get("scars") or []):
        return _proposal(
            "CONTRACT_POST",
            target_id=home_org_id,
            arguments={
                "org_id": home_org_id,
                "contract_kind": "ATTEST_ROOM",
                "target_count": 2,
                "reward_resource": "storage",
                "reward_amount": 2,
            },
        )

    # 3. Civic Exchange storefront-coupled contracts: CRAFT_ITEM (RFC-0144) and DELIVER_LOT.
    if room_id != "room.civic-exchange":
        return None
    if world_map is not None and "CRAFT_ITEM" not in open_kinds and (t_energy >= 6 or t_storage >= 4):
        needed_arch = _missing_cohort_archetype(world_map)
        if needed_arch:
            reward_res = "energy" if t_energy >= 6 else "storage"
            reward_amt = 6 if reward_res == "energy" else 4
            return _proposal(
                "CONTRACT_POST",
                target_id=home_org_id,
                arguments={
                    "org_id": home_org_id,
                    "contract_kind": "CRAFT_ITEM",
                    "target_item_archetype": needed_arch,
                    "reward_resource": reward_res,
                    "reward_amount": reward_amt,
                },
            )
    if t_energy >= 6 and "DELIVER_LOT" not in open_kinds:
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
