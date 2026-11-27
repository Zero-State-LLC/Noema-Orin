"""T6 (#160) m03 fleet-aware crafting, m04 state-delta supersession, and m05 grounded market/contract Herald digests."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from noema_orin.memory import Memory, WorldMap
from noema_orin.orin_adapter import (
    _changed_published_subjects,
    _one_record_per_subject,
    grounded_market_and_contract_digest,
    grounded_notice,
)
from noema_orin.shop_planner import plan_equipment_step

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None


class FleetAwareCraftingAndFulfillTests(unittest.TestCase):
    def test_m03_crafts_for_open_craft_item_contract_and_fulfills_when_carried(self):
        with tempfile.TemporaryDirectory() as d:
            wm = WorldMap(Path(d))
            try:
                canon_ws = {
                    "location": {
                        "room_id": "room.civic-exchange",
                        "entities": [{"entity_id": "entity.ws.1", "infra_type": "workshop", "condition": 90}],
                    },
                    "resources": {"energy": 12, "compute": 6},
                    "equipment": {"TOOL_SLOT": {"item_id": "item.welder.1"}},
                    "inventory": [
                        {"item_id": "item.welder.1", "archetype": "arc_welder", "equipped_slot": "TOOL_SLOT", "condition": 95},
                        {"item_id": "item.cell.1", "archetype": "power_cell", "condition": 100},
                    ],
                    "material_lots": [
                        {"material": "FERROUS_ORE", "amount": 4},
                        {"material": "SILICA_CELL", "amount": 4},
                        {"material": "SALVAGE_COMPOSITE", "amount": 4},
                    ],
                    "open_contracts": [
                        {
                            "contract_id": "contract.42",
                            "room_id": "room.civic-exchange",
                            "kind": "CRAFT_ITEM",
                            "target_item_archetype": "chrono_lens",
                            "status": "OPEN",
                        }
                    ],
                }
                # 1. Does not yet carry chrono_lens -> crafts chrono_lens for the contract
                p_craft = plan_equipment_step("custodian", canon_ws, {"battery_reserve_target": 1}, world_map=wm)
                act1 = p_craft.action if hasattr(p_craft, "action") else p_craft["action"]
                args1 = p_craft.arguments if hasattr(p_craft, "arguments") else p_craft["arguments"]
                self.assertEqual(act1, "CRAFT")
                self.assertEqual(args1["recipe_id"], "chrono_lens")

                # 2. Once SOUND+ chrono_lens is in inventory at the contract's room -> CONTRACT_FULFILL
                canon_ws["inventory"].append(
                    {"item_id": "item.lens.9", "archetype": "chrono_lens", "condition": 100}
                )
                p_ful = plan_equipment_step("custodian", canon_ws, {"battery_reserve_target": 1}, world_map=wm)
                act2 = p_ful.action if hasattr(p_ful, "action") else p_ful["action"]
                args2 = p_ful.arguments if hasattr(p_ful, "arguments") else p_ful["arguments"]
                self.assertEqual(act2, "CONTRACT_FULFILL")
                self.assertEqual(args2["contract_id"], "contract.42")
            finally:
                wm.close()

    def test_m03_crafts_missing_cohort_loadout_from_shared_map(self):
        with tempfile.TemporaryDirectory() as d:
            wm = WorldMap(Path(d))
            try:
                wm.locate("player.Cantor-Speaker", "room.hub", 10, 16, 20)
                canon_ws = {
                    "location": {
                        "room_id": "room.workshop",
                        "entities": [{"entity_id": "entity.ws.1", "infra_type": "workshop", "condition": 90}],
                    },
                    "resources": {"energy": 12, "compute": 6},
                    "equipment": {"TOOL_SLOT": {"item_id": "item.welder.1"}},
                    "inventory": [
                        {"item_id": "item.welder.1", "archetype": "arc_welder", "equipped_slot": "TOOL_SLOT", "condition": 95},
                        {"item_id": "item.cell.1", "archetype": "power_cell", "condition": 100},
                    ],
                    "material_lots": [
                        {"material": "FERROUS_ORE", "amount": 4},
                        {"material": "SILICA_CELL", "amount": 4},
                        {"material": "SALVAGE_COMPOSITE", "amount": 4},
                    ],
                }
                p = plan_equipment_step("custodian", canon_ws, {"battery_reserve_target": 1}, world_map=wm)
                act = p.action if hasattr(p, "action") else p["action"]
                args = p.arguments if hasattr(p, "arguments") else p["arguments"]
                self.assertEqual(act, "CRAFT")
                self.assertEqual(args["recipe_id"], "signal_transceiver")
            finally:
                wm.close()


class ArchivistDeltaSupersessionTests(unittest.TestCase):
    def test_m04_allows_supersede_only_when_subject_state_fingerprint_changes(self):
        with tempfile.TemporaryDirectory() as d:
            mem = Memory(Path(d))
            try:
                canon_v1 = {
                    "sequence": 100,
                    "location": {
                        "room_id": "room.relay",
                        "entities": [{"entity_id": "entity.relay-7", "condition": 85}],
                    },
                    "scars": [],
                    "contests": [],
                }
                # Record initial published state at cond bucket 80 (85 // 20 * 20 = 80)
                mem.remember("entity.relay-7|cond=80|scars=0|contests=0", kind="subject_state", room=None, sequence=100)
                published = {"entity.relay-7", "revised:entity.relay-7"}
                menu = [{"i": 0, "action": "RECONSTRUCT_SUPERSEDE", "raw": {"subject_ref": "entity.relay-7"}}]

                # Same state -> supersede stays suppressed (no D-070 churn)
                changed_v1 = _changed_published_subjects(canon_v1, mem)
                self.assertEqual(changed_v1, set())
                self.assertEqual(_one_record_per_subject(menu, published, changed_subjects=changed_v1), [])

                # Entity degrades to condition 35 + scar forms -> fingerprint changed -> supersede re-unlocked!
                canon_v2 = {
                    "sequence": 140,
                    "location": {
                        "room_id": "room.relay",
                        "entities": [{"entity_id": "entity.relay-7", "condition": 35}],
                    },
                    "scars": [{"scar_id": "scar.9", "strength": 0.4}],
                    "contests": [],
                }
                changed_v2 = _changed_published_subjects(canon_v2, mem)
                self.assertEqual(changed_v2, {"entity.relay-7"})
                kept = _one_record_per_subject(menu, published, changed_subjects=changed_v2)
                self.assertEqual(len(kept), 1)
                self.assertEqual(kept[0]["action"], "RECONSTRUCT_SUPERSEDE")
            finally:
                mem.close()


class SpeakerGroundedMarketDigestTests(unittest.TestCase):
    def test_m05_publishes_grounded_trade_and_contract_digest_with_seq_citation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wm = WorldMap(root)
            mem = Memory(root / "mind")
            try:
                wm.observe_market_and_equipment(
                    "room.civic-exchange",
                    "player.Tallow-Quartermaster",
                    {
                        "sequence": 512,
                        "location": {
                            "entities": [{"entity_id": "entity.stall-1", "infra_type": "barter_stall", "condition": 95}]
                        },
                        "shop_listings": [
                            {
                                "listing_id": "list.swap.1",
                                "stall_id": "entity.stall-1",
                                "listing_kind": "CORE_SWAP",
                                "offer_asset": {"kind": "ITEM", "predicate": {"archetype": "power_cell"}},
                                "ask_asset": {"kind": "ITEM", "predicate": {"archetype": "depleted_cell"}},
                                "fills_remaining": 1,
                            },
                            {
                                "listing_id": "list.sell.1",
                                "stall_id": "entity.stall-1",
                                "listing_kind": "SELL_OFFER",
                                "offer_asset": {"kind": "ITEM", "predicate": {"archetype": "chrono_lens"}},
                                "ask_asset": {"kind": "LOT", "material": "FERROUS_ORE", "amount": 5},
                                "fills_remaining": 1,
                            },
                        ],
                    },
                )
                canon = {
                    "sequence": 515,
                    "open_contracts": [{"contract_id": "c.1", "kind": "CRAFT_ITEM", "target_item_archetype": "chrono_lens"}],
                }
                digest_text = grounded_market_and_contract_digest(mem, wm, canon, org_name="Reach Compact")
                self.assertIsNotNone(digest_text)
                self.assertIn("observed at seq 512", digest_text)
                self.assertIn("CORE_SWAP", digest_text)
                self.assertIn("CRAFT_ITEM", digest_text)
                self.assertLessEqual(len(digest_text), 280)
                # Deduplicated once noticed until state changes
                self.assertIsNone(grounded_market_and_contract_digest(mem, wm, canon, org_name="Reach Compact"))
                # grounded_notice also surfaces market digest when world_map is supplied
                wm.observe_market_and_equipment(
                    "room.civic-exchange",
                    "player.Tallow-Quartermaster",
                    {
                        "sequence": 520,
                        "location": {
                            "entities": [{"entity_id": "entity.stall-1", "infra_type": "barter_stall", "condition": 95}]
                        },
                        "shop_listings": [
                            {
                                "listing_id": "list.buy.2",
                                "stall_id": "entity.stall-1",
                                "listing_kind": "BUY_ORDER",
                                "offer_asset": {"kind": "RESOURCE", "resource": "energy", "amount": 6},
                                "ask_asset": {"kind": "LOT", "material": "SALVAGE_COMPOSITE", "amount": 3},
                                "fills_remaining": 1,
                            }
                        ],
                    },
                )
                n2 = grounded_notice(mem, "Reach Compact", world_map=wm, canonical=canon)
                self.assertIsNotNone(n2)
                self.assertIn("observed at seq 520", n2)
            finally:
                wm.close()
                mem.close()


if __name__ == "__main__":
    unittest.main()
