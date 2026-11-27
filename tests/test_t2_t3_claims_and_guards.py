"""T2 (#156) shared map cohort_claims/shared_work and T3 (#157) pre-flight rejection guards."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from noema_orin.memory import WorldMap
from noema_orin.metrics import collect, digest, open_db
from noema_orin.orin_adapter import _can_supply, _options
from noema_orin.planner import route
from noema_orin.players import member_phase_jitter, stagger

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None


class SharedClaimsAndCrossCohortWorkTests(unittest.TestCase):
    def test_cohort_claims_lease_blocks_peers_until_expiry(self):
        with tempfile.TemporaryDirectory() as d:
            wm = WorldMap(Path(d))
            try:
                self.assertTrue(wm.claim_target("entity.relay-7", "player.m03", "REPAIR", current_seq=100, ttl=8))
                # Peer cannot steal active lease
                self.assertFalse(wm.claim_target("entity.relay-7", "player.m06", "REPAIR", current_seq=104, ttl=8))
                # Owner can refresh lease
                self.assertTrue(wm.claim_target("entity.relay-7", "player.m03", "REPAIR", current_seq=105, ttl=8))
                # Active claims exclude self when asked
                self.assertIn("entity.relay-7", wm.active_claims(106, exclude_member="player.m06"))
                self.assertNotIn("entity.relay-7", wm.active_claims(106, exclude_member="player.m03"))
                # After expiry (105 + 8 = 113), peer can claim
                self.assertTrue(wm.claim_target("entity.relay-7", "player.m06", "REPAIR", current_seq=113, ttl=8))
                wm.release_claim("entity.relay-7", member="player.m06")
                self.assertEqual(wm.active_claims(114), {})
            finally:
                wm.close()

    def test_surveyor_observed_damaged_infra_routes_custodian(self):
        with tempfile.TemporaryDirectory() as d:
            wm = WorldMap(Path(d))
            try:
                wm.observe("room.hub", "Hub", 10, ["room.east", "room.west"], ["MOVE"])
                wm.observe("room.east", "East", 12, ["room.hub"], ["MOVE"])
                wm.observe("room.west", "West", 5, ["room.hub"], ["MOVE"])
                # m06 surveyor observes damaged relay in room.east
                n = wm.observe_shared_work(
                    "room.east",
                    "player.Perigee-Surveyor",
                    {
                        "sequence": 15,
                        "location": {
                            "room_id": "room.east",
                            "entities": [
                                {"entity_id": "entity.relay-9", "entity_type": "INFRASTRUCTURE", "infra_type": "relay", "condition": 45},
                                {"entity_id": "entity.gen-ok", "entity_type": "INFRASTRUCTURE", "infra_type": "generator", "condition": 95},
                            ],
                        },
                    },
                )
                self.assertEqual(n, 1)
                canon = {
                    "location": {
                        "room_id": "room.hub",
                        "exits": [
                            {"direction": "east", "to_room_id": "room.east"},
                            {"direction": "west", "to_room_id": "room.west"},
                        ],
                    }
                }
                # Custodian routes east toward m06's discovered damaged relay
                self.assertEqual(
                    route(canon, wm, {"REPAIR", "RESTORE"}, explorer=False, me="player.Rivet-Custodian", current_seq=16),
                    "east",
                )
                # If another member claims entity.relay-9, custodian skips it
                wm.claim_target("entity.relay-9", "player.other", "REPAIR", current_seq=16, ttl=10)
                self.assertNotEqual(
                    route(canon, wm, {"REPAIR", "RESTORE"}, explorer=False, me="player.Rivet-Custodian", current_seq=17),
                    "east",
                )
            finally:
                wm.close()


class PreFlightRejectionGuardTests(unittest.TestCase):
    def test_options_filters_affordances_exceeding_live_budgets(self):
        canon = {
            "resources": {"energy": 4, "attention": 1, "compute": 1, "storage": 16},
            "affordances": [
                {"action": "RECONSTRUCT_SUPERSEDE", "available": True, "requires": {"attention": 2, "compute": 1}},
                {"action": "REFINE", "available": True, "requires": {"energy": 5, "compute": 1}},
                {"action": "WAIT", "available": True, "requires": {"energy": 0}},
            ],
        }
        opts = _options(canon, frozenset({"RECONSTRUCT_SUPERSEDE", "REFINE", "WAIT"}))
        self.assertEqual([o["action"] for o in opts], ["WAIT"])

    def test_can_supply_enforces_colocation_office_and_vault_floor(self):
        opt = {"action": "SUPPLY", "target_id": "player.Rivet-Custodian", "raw": {"resource": "storage"}}
        base_canon = {
            "self": "player.Tallow-Quartermaster",
            "players_here": [{"player_id": "player.Rivet-Custodian", "handle": "Rivet-Custodian"}],
            "organizations": [
                {
                    "org_id": "org.compact",
                    "treasury": {"storage": 2},
                    "offices": [
                        {
                            "office_id": "office.qm",
                            "authority_profile": "OPERATE_RESOURCE_ACCOUNT",
                            "status": "OCCUPIED",
                            "holder_id": "player.Tallow-Quartermaster",
                            "holder_handle": "Tallow-Quartermaster",
                        }
                    ],
                }
            ],
        }
        ok, amount = _can_supply(opt, base_canon)
        self.assertTrue(ok)
        self.assertEqual(amount, 2)  # clamped to live vault balance

        # Not co-located -> False
        not_here = {**base_canon, "players_here": []}
        self.assertFalse(_can_supply(opt, not_here)[0])

        # Empty vault -> False
        empty_vault = {
            **base_canon,
            "organizations": [{**base_canon["organizations"][0], "treasury": {"storage": 0}}],
        }
        self.assertFalse(_can_supply(opt, empty_vault)[0])

        # Does not hold OPERATE_RESOURCE_ACCOUNT -> False
        wrong_holder = {
            **base_canon,
            "organizations": [
                {
                    **base_canon["organizations"][0],
                    "offices": [{**base_canon["organizations"][0]["offices"][0], "holder_id": "player.other", "holder_handle": "other"}],
                }
            ],
        }
        self.assertFalse(_can_supply(opt, wrong_holder)[0])

    def test_phase_jitter_is_deterministic_and_metrics_tracks_stale_head_rate(self):
        j1 = member_phase_jitter("m01", 8.0)
        j2 = member_phase_jitter("m02", 8.0)
        self.assertNotEqual(j1, j2)
        self.assertEqual(j1, member_phase_jitter("m01", 8.0))
        cool, off = stagger(["m01", "m02", "m03"], "m02", 20, 8, jitter_s=1.3)
        self.assertEqual(cool, 24)
        self.assertEqual(off, 9.3)

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "logs").mkdir()
            rows = [
                {"member": "m06", "role": "surveyor", "persona_version": 1},
                *[{"turn": i, "action": "MOVE"} for i in range(1, 11)],
                {
                    "member": "m06",
                    "role": "surveyor",
                    "actions": 10,
                    "stop_reason": "duration_elapsed",
                    "rejections": {"by_verb_code": {"MOVE:STALE_HEAD": 2, "WAIT:STALE_HEAD": 1, "LOOK:BUDGET_EXCEEDED": 1}},
                },
            ]
            (root / "logs" / "noema-player@m06.log").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            db = open_db(root)
            try:
                collect(root, db)
                m06 = digest(db)["members"]["m06"]
                self.assertEqual(m06["stale_head_rejections"], 3)
                self.assertEqual(m06["stale_head_rate"], 0.3)
            finally:
                db.close()

    @unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
    def test_plan_skips_recharge_without_ready_generator_and_checks_office_act_org_id(self):
        from noema_orin.orin_adapter import OrinAdapter, _proposal

        ad = OrinAdapter(base_url="http://127.0.0.1:9/v1", model="m", brief="b")
        ad.allowed = frozenset({"LOOK", "WAIT", "MOVE", "RECHARGE"})
        ad.verbs = {"RECHARGE"}
        # Low energy with RECHARGE option advertised, but NO operational generator in room -> must WAIT, not RECHARGE
        canon = {
            "sequence": 10,
            "location": {"room_id": "room.dry", "name": "Dry", "exits": [], "entities": []},
            "resources": {"energy": 0, "storage": 16, "compute": 5},
            "affordances": [{"action": "RECHARGE", "operation": "RECHARGE", "available": True}],
        }
        prop = ad.decide({"canonical": canon})
        self.assertEqual(prop.action, "WAIT")

        # ORG_OFFICE_ACT missing org_id must return None instead of INVALID_REQUEST
        bad_raw = {"action": "ORG_OFFICE_ACT", "operation": "ORG_OFFICE_ACT", "cmd": 'notice ""', "available": True}
        self.assertIsNone(_proposal({"action": "ORG_OFFICE_ACT", "raw": bad_raw}, {}, None))


if __name__ == "__main__":
    unittest.main()
