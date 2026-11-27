"""T4 (#158) m02 complete storefront and T5 (#159) m01 civic contracts, OPEN_CHARTER & colocated diplomacy."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from noema_orin.memory import Memory, WorldMap
from noema_orin.planner import refine
from noema_orin.shop_planner import (
    plan_civic_contract,
    plan_founder_governance_and_commemorate,
    plan_quartermaster_shop,
    quartermaster_needs_shop_visit,
)


class QuartermasterStorefrontTests(unittest.TestCase):
    def _base_stall_canon(self, *, stall_items=None, listings=None, inv=None, energy=30):
        return {
            "location": {
                "room_id": "room.civic-exchange",
                "entities": [
                    {
                        "entity_id": "entity.stall-1",
                        "infra_type": "barter_stall",
                        "condition": 95,
                        "resources": {"energy": 12},
                        "inventory": stall_items or [],
                    }
                ],
            },
            "resources": {"energy": energy, "compute": 10},
            "inventory": inv or [],
            "shop_listings": listings or [],
        }

    def test_m02_publishes_core_swap_sell_offers_and_salvage_buy_order(self):
        # 1. Stall has a stocked power_cell -> lists CORE_SWAP first (1 power_cell <- 1 depleted_cell)
        canon = self._base_stall_canon(
            stall_items=[{"item_id": "item.cell.10", "archetype": "power_cell", "condition": 100}],
            listings=[],
        )
        p_swap = plan_quartermaster_shop(canon, {"shop_margin_bias": 0})
        args = p_swap.arguments if hasattr(p_swap, "arguments") else p_swap["arguments"]
        self.assertEqual(args["phase"], "list")
        self.assertEqual(args["listing_kind"], "CORE_SWAP")
        self.assertEqual(args["offer_asset"]["item_id"], "item.cell.10")
        self.assertEqual(args["ask_asset"]["predicate"]["archetype"], "depleted_cell")

        # 2. CORE_SWAP already open + second stocked power_cell -> lists SELL_OFFER for power_cell
        core_swap_listing = {
            "listing_id": "list.swap.1",
            "stall_id": "entity.stall-1",
            "listing_kind": "CORE_SWAP",
            "offer_asset": {"kind": "ITEM", "item_id": "item.cell.10"},
            "ask_asset": {"kind": "ITEM", "predicate": {"archetype": "depleted_cell"}},
            "fills_remaining": 1,
        }
        canon2 = self._base_stall_canon(
            stall_items=[
                {"item_id": "item.cell.10", "archetype": "power_cell", "condition": 100},
                {"item_id": "item.cell.11", "archetype": "power_cell", "condition": 100},
            ],
            listings=[core_swap_listing],
        )
        p_sell_cell = plan_quartermaster_shop(canon2, {"shop_margin_bias": 1})
        args2 = p_sell_cell.arguments if hasattr(p_sell_cell, "arguments") else p_sell_cell["arguments"]
        self.assertEqual(args2["phase"], "list")
        self.assertEqual(args2["listing_kind"], "SELL_OFFER")
        self.assertEqual(args2["offer_asset"]["item_id"], "item.cell.11")
        self.assertEqual(args2["ask_asset"]["amount"], 4)  # BASE 3 + bias 1

        # 3. Stocked non-loadout tool gets SELL_OFFER at tool_lot_price
        sell_cell_listing = {
            "listing_id": "list.sell.1",
            "stall_id": "entity.stall-1",
            "listing_kind": "SELL_OFFER",
            "offer_asset": {"kind": "ITEM", "item_id": "item.cell.11"},
            "ask_asset": {"kind": "LOT", "material": "FERROUS_ORE", "amount": 4},
            "fills_remaining": 1,
        }
        canon3 = self._base_stall_canon(
            stall_items=[
                {"item_id": "item.cell.10", "archetype": "power_cell", "condition": 100},
                {"item_id": "item.cell.11", "archetype": "power_cell", "condition": 100},
                {"item_id": "item.lens.1", "archetype": "chrono_lens", "condition": 90},
            ],
            listings=[core_swap_listing, sell_cell_listing],
        )
        p_sell_tool = plan_quartermaster_shop(canon3, {"shop_margin_bias": 0})
        args3 = p_sell_tool.arguments if hasattr(p_sell_tool, "arguments") else p_sell_tool["arguments"]
        self.assertEqual(args3["listing_kind"], "SELL_OFFER")
        self.assertEqual(args3["offer_asset"]["item_id"], "item.lens.1")
        self.assertEqual(args3["ask_asset"]["amount"], 5)

        # 4. Once FERROUS_ORE BUY_ORDER exists, posts SALVAGE_COMPOSITE BUY_ORDER
        ore_buy = {
            "listing_id": "list.buy.ore",
            "stall_id": "entity.stall-1",
            "listing_kind": "BUY_ORDER",
            "offer_asset": {"kind": "RESOURCE", "resource": "energy", "amount": 6},
            "ask_asset": {"kind": "LOT", "material": "FERROUS_ORE", "amount": 3},
            "fills_remaining": 1,
        }
        canon4 = self._base_stall_canon(stall_items=[], listings=[ore_buy])
        p_salv = plan_quartermaster_shop(canon4, {"shop_margin_bias": 0})
        args4 = p_salv.arguments if hasattr(p_salv, "arguments") else p_salv["arguments"]
        self.assertEqual(args4["listing_kind"], "BUY_ORDER")
        self.assertEqual(args4["ask_asset"]["material"], "SALVAGE_COMPOSITE")

    def test_m02_stocks_surplus_non_loadout_tool_and_knows_when_to_visit_shop(self):
        canon = self._base_stall_canon(
            inv=[
                {"item_id": "item.cutter.1", "archetype": "plasma_cutter", "condition": 95},  # QM loadout -> keep
                {"item_id": "item.lens.2", "archetype": "chrono_lens", "condition": 90},     # non-loadout -> stock
            ]
        )
        p = plan_quartermaster_shop(canon, {"battery_reserve_target": 1})
        args = p.arguments if hasattr(p, "arguments") else p["arguments"]
        self.assertEqual(args["phase"], "stock")
        self.assertEqual(args["asset"]["item_id"], "item.lens.2")

        with tempfile.TemporaryDirectory() as d:
            wm = WorldMap(Path(d))
            try:
                self.assertTrue(
                    quartermaster_needs_shop_visit(
                        {"location": {"room_id": "room.salvage"}, "inventory": canon["inventory"]},
                        wm,
                        {"battery_reserve_target": 1},
                    )
                )
            finally:
                wm.close()


class FounderContractsGovernanceAndDiplomacyTests(unittest.TestCase):
    def test_m01_posts_craft_item_repair_target_and_attest_room_contracts(self):
        with tempfile.TemporaryDirectory() as d:
            wm = WorldMap(Path(d))
            try:
                # 1. Missing cohort loadout equipment -> CRAFT_ITEM at civic-exchange
                wm.locate("player.Vellum-Archivist", "room.archive", 10, 16, 5)
                canon_ex = {
                    "location": {"room_id": "room.civic-exchange", "entities": []},
                    "resources": {"compute": 5},
                    "open_contracts": [],
                    "organizations": [{"org_id": "org.compact.1", "treasury": {"energy": 12, "storage": 10}}],
                }
                p_craft = plan_civic_contract("founder", canon_ex, "org.compact.1", world_map=wm)
                args_c = p_craft.arguments if hasattr(p_craft, "arguments") else p_craft["arguments"]
                self.assertEqual(args_c["contract_kind"], "CRAFT_ITEM")
                self.assertIn(args_c["target_item_archetype"], ("chrono_lens", "cipher_spike", "power_cell"))

                # 2. Standing in room with damaged infra -> REPAIR_TARGET using exact engine field `entity_id`
                canon_dmg = {
                    "location": {
                        "room_id": "room.relay-quarter",
                        "entities": [{"entity_id": "entity.relay-7", "entity_type": "INFRASTRUCTURE", "infra_type": "relay", "condition": 45}],
                    },
                    "resources": {"compute": 5},
                    "open_contracts": [],
                    "organizations": [{"org_id": "org.compact.1", "treasury": {"energy": 12, "storage": 10}}],
                }
                p_rep = plan_civic_contract("founder", canon_dmg, "org.compact.1", world_map=wm)
                args_r = p_rep.arguments if hasattr(p_rep, "arguments") else p_rep["arguments"]
                self.assertEqual(args_r["contract_kind"], "REPAIR_TARGET")
                self.assertEqual(args_r["entity_id"], "entity.relay-7")

                # 3. Standing in scarred room -> ATTEST_ROOM
                canon_scar = {
                    "location": {"room_id": "room.scarred", "entities": []},
                    "scars": [{"scar_id": "scar.1", "domain": "economic", "strength": 0.4}],
                    "resources": {"compute": 5},
                    "open_contracts": [],
                    "organizations": [{"org_id": "org.compact.1", "treasury": {"energy": 12, "storage": 10}}],
                }
                p_att = plan_civic_contract("founder", canon_scar, "org.compact.1", world_map=wm)
                args_a = p_att.arguments if hasattr(p_att, "arguments") else p_att["arguments"]
                self.assertEqual(args_a["contract_kind"], "ATTEST_ROOM")
            finally:
                wm.close()

    def test_m01_open_charter_and_commemorate_crystallized_lore(self):
        with tempfile.TemporaryDirectory() as d:
            mem = Memory(Path(d))
            try:
                canon_gov = {
                    "sequence": 40,
                    "location": {"room_id": "room.civic-exchange"},
                    "resources": {"compute": 5, "energy": 10},
                    "organizations": [
                        {
                            "org_id": "org.compact.1",
                            "offices": [{"office_id": "office.notice.1", "status": "OCCUPIED"}],
                            "governance_rule": None,
                        }
                    ],
                    "lore_attractors": [{"attractor_id": "lore.9", "label": "first relay", "basin": "crystallized"}],
                }
                p1 = plan_founder_governance_and_commemorate(
                    canon_gov, "org.compact.1", mem, [{"action": "ORG_GOVERNANCE_RULE"}]
                )
                act1 = p1.action if hasattr(p1, "action") else p1["action"]
                args1 = p1.arguments if hasattr(p1, "arguments") else p1["arguments"]
                self.assertEqual(act1, "ORG_GOVERNANCE_RULE")
                self.assertEqual(args1["rule"]["admission_mode"], "OPEN_CHARTER")

                # Second call skips already-published rule and commemorates crystallized lore
                p2 = plan_founder_governance_and_commemorate(
                    canon_gov, "org.compact.1", mem, [{"action": "COMMEMORATE", "target_id": "lore.9"}]
                )
                act2 = p2.action if hasattr(p2, "action") else p2["action"]
                self.assertEqual(act2, "COMMEMORATE")
                # Third call is idempotent (already commemorated)
                self.assertIsNone(
                    plan_founder_governance_and_commemorate(
                        canon_gov, "org.compact.1", mem, [{"action": "COMMEMORATE", "target_id": "lore.9"}]
                    )
                )
            finally:
                mem.close()

    def test_refine_requires_colocation_for_agreements_and_allows_external_non_blocked_players(self):
        canon = {
            "organizations": [],
            "players_here": [
                {"player_id": "player.q", "handle": "q"},
                {"player_id": "player.visitor", "handle": "visitor"},
            ],
        }
        mk = lambda t, p: {"action": "AGREEMENT_FORM", "target_id": p, "raw": {"agreement_type": t, "player_id": p}}
        opts = [
            mk("TRADE", "player.q"),             # blocked agreement type
            mk("access", "player.visitor"),      # blocked agreement type
            mk("NON_AGGRESSION", "player.away"), # NOT co-located -> dropped!
            mk("NON_AGGRESSION", "player.visitor"),  # co-located external player -> kept!
            mk("MUTUAL_DEFENSE", "player.q"),        # co-located cohort -> kept!
        ]
        out = refine(opts, canon, {"player.q"})
        self.assertEqual(
            [(o["raw"]["agreement_type"], o["target_id"]) for o in out],
            [("NON_AGGRESSION", "player.visitor"), ("MUTUAL_DEFENSE", "player.q")],
        )


if __name__ == "__main__":
    unittest.main()
