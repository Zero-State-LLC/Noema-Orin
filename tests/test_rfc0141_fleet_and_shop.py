import tempfile
import unittest
from importlib.util import find_spec
from pathlib import Path

from noema_orin.memory import WorldMap
from noema_orin.players import build_policy
from noema_orin.roles import DENY_ALWAYS, role_for
from noema_orin.rsi import (
    KNOB_SPECS,
    MAX_UNEQUIPPED_BROKEN_TOOL_TURNS,
    RsiRatchet,
    apply_knob_deltas,
    build_session_dossier,
    default_knobs,
)
from noema_orin.shop_planner import (
    ROLE_LOADOUTS,
    compute_shop_prices,
    count_unequipped_broken_tools,
    plan_civic_contract,
    plan_equipment_step,
    plan_quartermaster_shop,
    plan_warden_defense_and_sanction,
)

_HAS_CLIENT = find_spec("noema_client") is not None


class Rfc0141FleetAndShopTests(unittest.TestCase):
    def test_roles_and_loadouts_consolidated_into_6_units_plus_maintenance(self):
        self.assertEqual(
            set(ROLE_LOADOUTS),
            {"founder", "quartermaster", "custodian", "archivist", "speaker", "surveyor", "maintenance"},
        )
        self.assertIn("barter_stall", role_for("quartermaster")["builds"])
        self.assertIn("CONTEST_DEFEND", role_for("surveyor")["allow"])
        self.assertIn("SANCTION", role_for("surveyor")["allow"])
        self.assertNotIn("CONTEST_DECLARE", role_for("surveyor")["allow"])
        self.assertIn("CONTEST_DECLARE", DENY_ALWAYS)
        self.assertIn("TRADE_PROPOSE", DENY_ALWAYS)
        # Operator maintenance remains strictly bounded
        self.assertEqual(
            set(role_for("maintenance")["allow"]),
            {"LOOK", "INSPECT", "WAIT", "ENTER_WORLD", "OBSERVE", "HARVEST", "COMMIT.HARVEST"},
        )

    @unittest.skipUnless(_HAS_CLIENT, "needs noema-client v0.2.0")
    def test_granular_client_policy_per_role(self):
        qm = build_policy("quartermaster")
        self.assertFalse(qm.allow_trade_p2p)
        self.assertTrue(qm.allow_shop_manage)
        self.assertTrue(qm.allow_shop_fulfill)
        self.assertTrue(qm.allow_agreement)
        self.assertFalse(qm.allow_contest_declare)
        self.assertTrue(qm.allow_items)

        surv = build_policy("surveyor")
        self.assertFalse(surv.allow_contest_declare)
        self.assertTrue(surv.allow_contest_defend)
        self.assertFalse(surv.allow_shop_manage)
        self.assertTrue(surv.allow_shop_fulfill)

        maint = build_policy("maintenance")
        self.assertFalse(maint.allow_shop_fulfill)
        self.assertFalse(maint.allow_shop_manage)
        self.assertFalse(maint.allow_contest_defend)
        self.assertFalse(maint.allow_items)

    @unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
    def test_hidden_verbs_hide_shop_contracts_supply_and_sanction_from_llm(self):
        from noema_orin.orin_adapter import OrinAdapter

        ad = OrinAdapter(base_url="http://localhost:11434", model="test", brief="test")
        hidden = ad._hidden_verbs()
        for verb in ("SUPPLY", "CONTRACT_POST", "SANCTION", "TRADE"):
            self.assertIn(verb, hidden)

    def test_shop_planner_equipment_storefront_warden_and_contracts(self):
        prices_base = compute_shop_prices(0)
        prices_tight = compute_shop_prices(2)
        self.assertGreater(prices_tight["power_cell_lot_price"], prices_base["power_cell_lot_price"])
        self.assertLess(prices_tight["ore_buy_energy"], prices_base["ore_buy_energy"])

        # 1. Equipment upkeep: auto-equip loadout, recycle depleted cell at generator, repair broken tool at workshop
        canon_equip = {
            "location": {"room_id": "room.generator-hall", "entities": [{"entity_id": "entity.gen-1", "infra_type": "generator", "condition": 90}]},
            "resources": {"energy": 20, "compute": 10},
            "equipment": {},
            "inventory": [
                {"item_id": "item.cutter.1", "archetype": "plasma_cutter", "equip_slot": "TOOL_SLOT", "condition": 90},
                {"item_id": "item.dep.1", "archetype": "depleted_cell", "condition": 0},
            ],
        }
        p1 = plan_equipment_step("quartermaster", canon_equip, {"tool_repair_floor": 25})
        act1 = p1.action if hasattr(p1, "action") else p1["action"]
        self.assertEqual(act1, "EQUIP")

        canon_equip["equipment"] = {"TOOL_SLOT": {"item_id": "item.cutter.1"}}
        canon_equip["inventory"][0]["equipped_slot"] = "TOOL_SLOT"
        p2 = plan_equipment_step("quartermaster", canon_equip, {"tool_repair_floor": 25})
        act2 = p2.action if hasattr(p2, "action") else p2["action"]
        self.assertEqual(act2, "RECHARGE")

        # 2. Quartermaster storefront stocking & listing
        canon_shop = {
            "location": {"room_id": "room.civic-exchange", "entities": [{"entity_id": "entity.stall-1", "infra_type": "barter_stall", "condition": 95}]},
            "resources": {"energy": 30, "compute": 10},
            "inventory": [
                {"item_id": "item.cell.1", "archetype": "power_cell", "condition": 100},
                {"item_id": "item.cell.2", "archetype": "power_cell", "condition": 100},
            ],
            "shop_listings": [],
        }
        p_shop = plan_quartermaster_shop(canon_shop, {"battery_reserve_target": 1, "shop_margin_bias": 0})
        args_shop = p_shop.arguments if hasattr(p_shop, "arguments") else p_shop["arguments"]
        self.assertEqual(args_shop["phase"], "stock")
        self.assertEqual(args_shop["asset"]["item_id"], "item.cell.1")

        # 3. Warden defense & evidence-backed sanction (never CONTEST_DECLARE)
        canon_warden = {
            "self": "player.surveyor",
            "resources": {"energy": 20, "compute": 10},
            "contests": [
                {
                    "contest_id": "contest.9",
                    "status": "OPEN",
                    "declarer_id": "player.raider",
                    "contest_form": "RESOURCE_SEIZURE",
                    "target": {"kind": "HOLDING", "holder_id": "player.qm"},
                }
            ],
        }
        p_def = plan_warden_defense_and_sanction("surveyor", canon_warden, [], {"player.qm"})
        act_def = p_def.action if hasattr(p_def, "action") else p_def["action"]
        self.assertEqual(act_def, "CONTEST_DEFEND")

        p_sanc = plan_warden_defense_and_sanction(
            "surveyor",
            {"self": "player.surveyor", "resources": {"energy": 20, "compute": 10}, "contests": []},
            [{"action": "SANCTION", "target_id": "crime.42", "raw": {"detection_id": "crime.42"}}],
        )
        act_sanc = p_sanc.action if hasattr(p_sanc, "action") else p_sanc["action"]
        self.assertEqual(act_sanc, "SANCTION")

        # 4. Founder civic contract posting in Civic Exchange
        canon_contract = {
            "location": {"room_id": "room.civic-exchange"},
            "resources": {"compute": 5},
            "open_contracts": [],
            "organizations": [{"org_id": "org.compact.1", "treasury": {"energy": 12, "storage": 10}}],
        }
        p_con = plan_civic_contract("founder", canon_contract, "org.compact.1")
        act_con = p_con.action if hasattr(p_con, "action") else p_con["action"]
        self.assertEqual(act_con, "CONTRACT_POST")

    def test_map_db_market_and_equipment_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            wmap = WorldMap(Path(tmp))
            try:
                res = wmap.observe_market_and_equipment(
                    "room.civic-exchange",
                    "player.qm",
                    {
                        "sequence": 77,
                        "location": {
                            "entities": [
                                {"entity_id": "entity.stall-1", "infra_type": "barter_stall", "owner_id": "org.c", "condition": 92}
                            ]
                        },
                        "shop_listings": [
                            {
                                "listing_id": "list.1",
                                "stall_id": "entity.stall-1",
                                "owner_id": "org.c",
                                "listing_kind": "SELL_OFFER",
                                "offer_asset": {"kind": "RESOURCE", "resource": "energy", "amount": 5},
                                "ask_asset": {"kind": "LOT", "material": "FERROUS_ORE", "amount": 2},
                                "fills_remaining": 2,
                            }
                        ],
                        "inventory": [
                            {
                                "item_id": "item.cutter.1",
                                "archetype": "plasma_cutter",
                                "category": "TOOL",
                                "equip_slot": "TOOL_SLOT",
                                "equipped_slot": "TOOL_SLOT",
                                "condition": 85,
                                "max_condition": 100,
                            }
                        ],
                    },
                )
                self.assertEqual(res, {"stalls": 1, "listings": 1, "equipment": 1})
                self.assertEqual(len(wmap.observed_stalls()), 1)
                self.assertEqual(len(wmap.observed_listings(room_id="room.civic-exchange")), 1)
                self.assertEqual(wmap.observed_equipment("player.qm")[0]["archetype"], "plasma_cutter")
            finally:
                wmap.close()

    def test_rsi_knobs_and_broken_tool_canary_rollback(self):
        self.assertIn("tool_repair_floor", KNOB_SPECS)
        self.assertIn("battery_reserve_target", KNOB_SPECS)
        self.assertIn("shop_margin_bias", KNOB_SPECS)
        self.assertEqual(MAX_UNEQUIPPED_BROKEN_TOOL_TURNS, 12)

        knobs = default_knobs()
        nxt, ok = apply_knob_deltas(knobs, {"tool_repair_floor": 1, "battery_reserve_target": 1, "shop_margin_bias": 1})
        self.assertTrue(ok)
        self.assertEqual(nxt["tool_repair_floor"], 26)
        self.assertEqual(nxt["battery_reserve_target"], 2)
        self.assertEqual(nxt["shop_margin_bias"], 1)

        self.assertEqual(
            count_unequipped_broken_tools({"inventory": [{"item_id": "i1", "archetype": "arc_welder", "condition": 0}]}),
            1,
        )

        with tempfile.TemporaryDirectory() as tmp:
            mind = Path(tmp)
            ratchet = RsiRatchet(mind)
            persona = {"version": 1, "traits": {"caution": 0.5}}
            good_dossier = build_session_dossier(
                role="custodian",
                role_verbs={"REPAIR"},
                turn_log=[{"action": "REPAIR", "room": "r1", "seq": i, "budgets": {"energy": 10}} for i in range(1, 15)],
            )
            ratchet.evaluate_session(good_dossier, persona, knobs)
            ok_reg, _ = ratchet.register_candidate({"knob_deltas": {"tool_repair_floor": -1}}, 2)
            self.assertTrue(ok_reg)

            broken_dossier = build_session_dossier(
                role="custodian",
                role_verbs={"REPAIR"},
                turn_log=[
                    {"action": "REPAIR", "room": "r1", "seq": i, "budgets": {"energy": 10}, "unequipped_broken_tools": 1}
                    for i in range(1, 13)
                ],
            )
            self.assertEqual(broken_dossier["unequipped_broken_tool_turns"], 12)
            verdict = ratchet.evaluate_session(broken_dossier, {"version": 2}, nxt)
            self.assertEqual(verdict["verdict"], "ROLLED_BACK")
            self.assertIn("unequipped_broken_tool_turns=12", verdict["reason"])


if __name__ == "__main__":
    unittest.main()
