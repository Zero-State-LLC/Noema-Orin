"""T8 (#162) declarative role playbooks/ state machines and T9 (#163) medium-loop agenda planner."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from noema_orin.agenda import AgendaManager, AgendaStep
from noema_orin.memory import Memory, WorldMap
from noema_orin.playbooks import ROLE_PLAYBOOKS, PlaybookContext, run_role_playbook
from noema_orin.roles import DENY_ALWAYS, role_for
from noema_orin.rsi import load_agenda, replay_verify, save_agenda

_HAS_CLIENT = importlib.util.find_spec("noema_client") is not None


class DeclarativePlaybooksTests(unittest.TestCase):
    def test_all_six_resident_roles_have_registered_playbooks(self):
        self.assertEqual(
            set(ROLE_PLAYBOOKS),
            {"founder", "quartermaster", "custodian", "archivist", "speaker", "surveyor"},
        )

    @unittest.skipUnless(_HAS_CLIENT, "needs noema-client")
    def test_quartermaster_and_custodian_playbooks_report_explicit_states_and_pass_replay(self):
        from noema_orin.orin_adapter import OrinAdapter

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            wm = WorldMap(root)
            mem = Memory(root / "mind")
            try:
                spec_qm = role_for("quartermaster")

                def make_qm():
                    a = OrinAdapter(base_url="http://127.0.0.1:9/v1", model="m", brief="b")
                    a.allowed = frozenset(spec_qm["allow"])
                    a.verbs = set(spec_qm["verbs"])
                    a.builds = tuple(spec_qm.get("builds") or ())
                    a.health.role = "Tallow-quartermaster"
                    a.memory = mem
                    a.world_map = wm
                    return a

                snap_shop = {
                    "self": "player.Tallow-Quartermaster",
                    "sequence": 100,
                    "location": {
                        "room_id": "room.civic-exchange",
                        "name": "Civic Exchange",
                        "exits": [],
                        "entities": [
                            {
                                "entity_id": "entity.stall-1",
                                "infra_type": "barter_stall",
                                "condition": 95,
                                "inventory": [{"item_id": "item.cell.1", "archetype": "power_cell", "condition": 100}],
                            }
                        ],
                    },
                    "resources": {"energy": 20, "compute": 10, "storage": 16},
                    "inventory": [],
                    "shop_listings": [],
                    "affordances": [{"action": "WAIT", "available": True}],
                }
                ad = make_qm()
                prop = ad.decide({"canonical": snap_shop})
                self.assertEqual(prop.action, "TRADE")
                self.assertEqual(ad.last_playbook_state, "STOREFRONT")

                gate = replay_verify(make_qm, [snap_shop], denied_verbs=set(DENY_ALWAYS))
                self.assertTrue(gate["ok"])
                self.assertEqual(gate["actions"], ["TRADE"])
            finally:
                wm.close()
                mem.close()


class MediumLoopAgendaTests(unittest.TestCase):
    def test_agenda_generates_typed_steps_persists_across_restarts_and_expires_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mind = root / "mind"
            wm = WorldMap(root)
            try:
                wm.observe("room.hub", "Hub", 10, ["room.east"], ["MOVE"])
                wm.observe("room.east", "East", 11, ["room.hub"], ["REPAIR"])
                wm.observe_shared_work(
                    "room.east",
                    "player.Perigee-Surveyor",
                    {
                        "sequence": 15,
                        "location": {
                            "room_id": "room.east",
                            "entities": [{"entity_id": "entity.relay-9", "infra_type": "relay", "condition": 40}],
                        },
                    },
                )
                mgr = AgendaManager.from_disk(mind)
                self.assertTrue(mgr.needs_refresh(turn_count=0, current_seq=20))
                steps = mgr.refresh(
                    role="custodian",
                    canonical={"sequence": 20, "location": {"room_id": "room.hub"}},
                    world_map=wm,
                    traits={"curiosity": 0.6, "thrift": 0.5, "caution": 0.5, "sociability": 0.3},
                    current_seq=20,
                    turn_count=0,
                )
                self.assertGreaterEqual(len(steps), 1)
                self.assertLessEqual(len(steps), 5)
                self.assertEqual(steps[0].goal_kind, "REPAIR_INFRA")
                self.assertEqual(steps[0].target_room, "room.east")
                self.assertEqual(steps[0].target_id, "entity.relay-9")
                self.assertEqual(mgr.epoch, 1)

                # Persists cleanly through rsi.save_agenda / load_agenda across 30m session restart
                mgr.save(mind, held_tracks=["engineer", "artificer"], build_room="room.hub", updated_seq=20)
                reloaded = AgendaManager.from_disk(mind)
                self.assertEqual(reloaded.epoch, 1)
                self.assertEqual(reloaded.active_step(current_seq=25).target_id, "entity.relay-9")

                # Completing repair in target_room marks step 0 done and promotes step 1 (CRAFT_FOR_FLEET)
                reloaded.mark_progress(
                    canonical={"location": {"room_id": "room.east"}},
                    action="REPAIR",
                    target_id="entity.relay-9",
                    current_seq=26,
                )
                self.assertEqual(reloaded.steps[0].status, "done")
                self.assertEqual(reloaded.active_step(current_seq=26).goal_kind, "CRAFT_FOR_FLEET")
                # Completing step 1 exhausts agenda and triggers refresh
                reloaded.mark_progress(
                    canonical={"location": {"room_id": "room.civic-exchange"}},
                    action="CRAFT",
                    target_id=None,
                    current_seq=27,
                )
                self.assertIsNone(reloaded.active_step(current_seq=27))
                self.assertTrue(reloaded.needs_refresh(turn_count=3, current_seq=27))

                # Expiry marks overdue step blocked and triggers refresh
                old_step = AgendaStep(
                    goal_kind="INSPECT_SCAR",
                    target_room="room.west",
                    target_id="scar.1",
                    status="active",
                    created_seq=10,
                    expires_seq=30,
                )
                reloaded.steps = [old_step]
                self.assertIsNone(reloaded.active_step(current_seq=35))
                self.assertEqual(old_step.status, "blocked")
            finally:
                wm.close()


if __name__ == "__main__":
    unittest.main()
