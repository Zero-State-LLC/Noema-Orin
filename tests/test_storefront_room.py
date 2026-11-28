"""D-092: the storefront is wherever the Compact's barter stall stands, and serving a colocated peer beats walking.

Live evidence (2026-11-28): the only Compact barter stall is `entity.barter-stall.a1f880c3` in room.archive, with five
BUY_ORDER listings. Every storefront rule hard-coded room.civic-exchange and checked for listings there, found none, and
pulled m02 back: 18 of 18 replayed reversals were the RETURN_STOREFRONT rule. The stall entity also carries no
`infra_type` (only `label: "barter-stall"`), so the shared map never recorded it as a stall at all.
"""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from noema_orin.memory import WorldMap

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None
STALL = {"condition": 100, "entity_id": "entity.barter-stall.a1f880c3", "entity_type": "INFRASTRUCTURE",
         "harvestable": False, "label": "barter-stall", "repairable": False}
LISTING = {"ask_asset": {"amount": 3, "kind": "LOT", "material": "FERROUS_ORE"}, "fills_remaining": 1,
           "listing_id": "listing.aff795cc", "listing_kind": "BUY_ORDER", "max_fills": 1,
           "offer_asset": {"amount": 6, "kind": "RESOURCE", "resource": "energy"},
           "owner_id": "org.reach-compact.1", "stall_id": "entity.barter-stall.a1f880c3"}


class StallRecordedByLabel(unittest.TestCase):
    def test_label_only_stall_is_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            wm = WorldMap(Path(d))
            try:
                res = wm.observe_market_and_equipment(
                    "room.archive", "player.Vellum-Archivist",
                    {"sequence": 88746, "location": {"entities": [STALL]}, "shop_listings": [LISTING]})
                self.assertEqual(res["stalls"], 1)
                self.assertEqual([s["room_id"] for s in wm.observed_stalls()], ["room.archive"])
            finally:
                wm.close()


class StorefrontRoom(unittest.TestCase):
    def _map(self, d):
        wm = WorldMap(Path(d))
        wm.observe_market_and_equipment("room.archive", "player.Vellum-Archivist",
                                        {"sequence": 88746, "location": {"entities": [STALL]}, "shop_listings": [LISTING]})
        return wm

    def test_storefront_is_the_room_with_the_home_orgs_listings(self):
        from noema_orin.shop_planner import storefront_room

        with tempfile.TemporaryDirectory() as d:
            wm = self._map(d)
            try:
                self.assertEqual(storefront_room(wm, "org.reach-compact.1"), "room.archive")
                self.assertEqual(storefront_room(wm, None), "room.archive", "any recorded stall beats a guess")
            finally:
                wm.close()

    def test_listings_locate_the_storefront_without_a_stall_row(self):
        """Old-code agents delete label-only stall rows each visit; the listings still say where the stall is."""
        from noema_orin.shop_planner import storefront_room

        with tempfile.TemporaryDirectory() as d:
            wm = self._map(d)
            try:
                wm.db.execute("DELETE FROM shop_stalls")
                self.assertEqual(storefront_room(wm, "org.reach-compact.1"), "room.archive")
                self.assertEqual(storefront_room(wm, None), "room.archive")
            finally:
                wm.close()

    def test_no_stall_recorded_falls_back_to_civic_exchange(self):
        from noema_orin.shop_planner import STOREFRONT_DEFAULT, storefront_room

        with tempfile.TemporaryDirectory() as d:
            wm = WorldMap(Path(d))
            try:
                self.assertEqual(storefront_room(wm, "org.reach-compact.1"), STOREFRONT_DEFAULT)
                self.assertEqual(STOREFRONT_DEFAULT, "room.civic-exchange")
            finally:
                wm.close()

    def test_no_pull_when_the_stall_room_has_live_listings(self):
        from noema_orin.shop_planner import quartermaster_needs_shop_visit

        with tempfile.TemporaryDirectory() as d:
            wm = self._map(d)
            try:
                here = {"location": {"room_id": "room.storage-district"}, "inventory": []}
                self.assertFalse(quartermaster_needs_shop_visit(here, wm, {}),
                                 "the Compact's listings are live in room.archive; nothing to restock")
            finally:
                wm.close()

    def test_no_pull_while_standing_at_the_storefront(self):
        from noema_orin.shop_planner import quartermaster_needs_shop_visit

        with tempfile.TemporaryDirectory() as d:
            wm = WorldMap(Path(d))
            wm.observe_market_and_equipment("room.archive", "player.x", {"sequence": 1, "location": {"entities": [STALL]},
                                                                          "shop_listings": []})
            wm.observe("room.archive", "Archive", 1, ["room.civic-exchange"], [])
            wm.observe("room.civic-exchange", "Civic Exchange", 1, ["room.archive"], [])
            try:
                at_stall = {"location": {"room_id": "room.archive"}, "inventory": [], "resources": {"energy": 20}}
                self.assertFalse(quartermaster_needs_shop_visit(at_stall, wm, {}))
                away = {"location": {"room_id": "room.civic-exchange"}, "inventory": [], "resources": {"energy": 20}}
                self.assertTrue(quartermaster_needs_shop_visit(away, wm, {}),
                                "stall recorded with no live listings and energy to fund one: go restock it")
            finally:
                wm.close()

    def test_no_pull_to_an_empty_storefront_without_energy_to_list(self):
        """An empty storefront needs a funded BUY_ORDER (6 + 8 energy on arrival). At 5-7 energy m02 arrived,
        could do nothing, left and was pulled back again."""
        from noema_orin.shop_planner import quartermaster_needs_shop_visit

        with tempfile.TemporaryDirectory() as d:
            wm = WorldMap(Path(d))
            wm.observe_market_and_equipment("room.civic-exchange", "player.x",
                                            {"sequence": 1, "location": {"entities": [STALL]}, "shop_listings": []})
            wm.observe("room.civic-exchange", "Civic Exchange", 1, ["room.storage-district"], [])
            wm.observe("room.storage-district", "Storage District", 1, ["room.civic-exchange"], [])
            try:
                for energy in (5, 6, 7, 15):
                    away = {"location": {"room_id": "room.storage-district"}, "inventory": [],
                            "resources": {"energy": energy}}
                    self.assertFalse(quartermaster_needs_shop_visit(away, wm, {}), energy)
                self.assertTrue(quartermaster_needs_shop_visit(
                    {"location": {"room_id": "room.storage-district"}, "inventory": [], "resources": {"energy": 16}},
                    wm, {}), "16 - 2 for the hop leaves the 14 a BUY_ORDER needs")
            finally:
                wm.close()


@unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
class ServeBeforeWalking(unittest.TestCase):
    """A colocated custodian with need gets the SUPPLY before any storefront pull (m02 walked past it)."""

    def test_supply_colocated_custodian_before_return_storefront(self):
        from noema_orin.orin_adapter import OrinAdapter
        from noema_orin.roles import role_for

        spec = role_for("quartermaster")
        org = "org.reach-compact.1"
        obs = {
            "self": "player.Tallow-Quartermaster", "sequence": 87666, "cycle": 23036,
            "location": {"room_id": "room.storage-district", "entities": [],
                         "exits": [{"direction": "east", "to_room_id": "room.civic-exchange", "two_way": True}]},
            "resources": {"attention": 8, "compute": 64, "energy": 6, "influence": 40, "storage": 11},
            "players_here": [{"player_id": "player.Rivet-Custodian", "handle": "Rivet-Custodian"}],
            "organizations": [{"org_id": org, "my_role": "member", "treasury": {"storage": 57, "energy": 0},
                               "offices": [{"office_id": "office.q", "authority_profile": "OPERATE_RESOURCE_ACCOUNT",
                                            "status": "OCCUPIED", "holder_id": None,
                                            "holder_handle": "Tallow-Quartermaster"}]}],
            "affordances": [
                {"acting_for": org, "action": "SUPPLY", "available": True, "cmd": "supply player.Rivet-Custodian storage",
                 "kind": "org", "office_id": "office.q", "operation": "SUPPLY", "player_id": "player.Rivet-Custodian",
                 "requires": {"compute": 1}, "resource": "storage", "target_id": "player.Rivet-Custodian",
                 "target_label": "Rivet-Custodian", "verb": "COMMIT"},
                {"action": "MOVE", "available": True, "target_id": "east", "cmd": "move east"},
                {"action": "WAIT", "available": True},
            ],
            "inventory": [],
            "shop_listings": [],
        }
        with tempfile.TemporaryDirectory() as d:
            wm = WorldMap(Path(d))
            wm.observe("room.civic-exchange", "Civic Exchange", 1, ["room.storage-district"], [])
            wm.observe("room.storage-district", "Storage District", 1, ["room.civic-exchange"], [])
            wm.observe_market_and_equipment("room.civic-exchange", "player.x",
                                            {"sequence": 1, "location": {"entities": [dict(STALL, entity_id="e.s2")]},
                                             "shop_listings": []})
            wm.locate("player.Rivet-Custodian", "room.storage-district", 3, 14, 87660)  # 2 aboard < LOW_CARGO
            try:
                a = OrinAdapter(base_url="http://127.0.0.1:9/v1", model="m", brief="b")
                a.allowed = frozenset(spec["allow"])
                a.verbs = set(spec["verbs"])
                a.supply = set(spec.get("supply") or ())
                a.builds = tuple(spec.get("builds") or ())
                a.health.role = "Tallow-quartermaster"
                a.world_map = wm
                a.role_handles = {"custodian": "Rivet-Custodian"}
                import contextlib
                import io
                import json as _json

                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    p = a.decide({"canonical": obs})
                self.assertEqual((p.action, p.target_id), ("SUPPLY", "player.Rivet-Custodian"), a.last_playbook_state)
                self.assertEqual(a.last_playbook_state, "SUPPLY_PEER")
                turn = next(_json.loads(line) for line in buf.getvalue().splitlines() if line.startswith('{"turn"'))
                self.assertEqual(turn["step"], "SUPPLY_PEER", "the turn line names the rule that chose a planner turn")
            finally:
                wm.close()


if __name__ == "__main__":
    unittest.main()
