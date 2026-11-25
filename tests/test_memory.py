import os
import stat
import tempfile
import unittest
from pathlib import Path

from noema_orin.memory import Memory, WorldMap


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_facts_persist_across_instances_with_source_sequence_and_private_mode(self):
        Memory(self.root / "mind").remember("relay-7 condition 20%", kind="infra", room="room.relay-quarter", sequence=59801)
        again = Memory(self.root / "mind")
        hits = again.recall("relay condition")
        self.assertEqual(hits[0]["fact"], "relay-7 condition 20%")
        self.assertEqual(hits[0]["source_sequence"], 59801)
        self.assertEqual(stat.S_IMODE(os.stat(self.root / "mind" / "memory.db").st_mode), 0o600)

    def test_current_observation_wins_and_stale_facts_are_not_recalled(self):
        m = Memory(self.root / "mind")
        m.remember("salvage cache stock 3", kind="stock", room="room.ruin-shelf", sequence=1)
        m.mark_stale(kind="stock", room="room.ruin-shelf", keep={"salvage cache stock 0"})
        self.assertEqual(m.recall("salvage cache"), [])

    def test_duplicate_fact_refreshes_instead_of_duplicating(self):
        m = Memory(self.root / "mind")
        for seq in (1, 2, 3):
            m.remember("Civic Exchange offers ORG_CREATE", kind="offer", room="room.civic-exchange", sequence=seq)
        hits = m.recall("ORG_CREATE")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["source_sequence"], 3)

    def test_relations_keep_contradictory_evidence(self):
        m = Memory(self.root / "mind")
        m.note_player("player.x", "shared stock", sign=1, sequence=1)
        m.note_player("player.x", "broke agreement", sign=-1, sequence=2)
        self.assertEqual(m.relations("player.x"), {"supporting": 1, "opposing": 1, "contested": True})


class WorldMapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.map = WorldMap(Path(self.tmp.name))
        self.map.observe("room.civic-exchange", "Civic Exchange", 10, ["room.transit-ring"], ["ORG_CREATE", "MOVE"])
        self.map.observe("room.transit-ring", "Transit Ring", 11, ["room.civic-exchange", "room.relay-quarter"], ["MOVE"])
        self.map.observe("room.relay-quarter", "Relay Quarter", 12, ["room.transit-ring"], ["REPAIR", "MOVE"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_finds_room_offering_role_verbs_and_routes_there(self):
        goal = self.map.where_offered({"REPAIR", "RESTORE"}, exclude="room.civic-exchange")
        self.assertEqual(goal, "room.relay-quarter")
        self.assertEqual(self.map.next_hop("room.civic-exchange", goal), "room.transit-ring")
        self.assertEqual(self.map.next_hop("room.transit-ring", goal), "room.relay-quarter")

    def test_least_recently_seen_prefers_unknown_rooms(self):
        self.assertEqual(self.map.least_recent(["room.relay-quarter", "room.archive"]), "room.archive")

    def test_shared_between_agents(self):
        other = WorldMap(Path(self.tmp.name))
        self.assertEqual(other.where_offered({"ORG_CREATE"}), "room.civic-exchange")


if __name__ == "__main__":
    unittest.main()


class CompactTests(unittest.TestCase):
    def test_keeps_newest_reading_and_bounds_stale(self):
        import tempfile
        from pathlib import Path

        from noema_orin.memory import Memory
        with tempfile.TemporaryDirectory() as d:
            m = Memory(Path(d))
            for seq, n in ((1, 10), (2, 11), (3, 12)):
                m.remember(f"Salvage Cache holds {n} materials available to harvest.", kind="consequence", room="r", sequence=seq)
            m.remember("Relay Quarter offers HARVEST", kind="offer", room="r", sequence=1)
            for i in range(5):
                m.remember(f"old {i}", kind="offer", room="r2", sequence=i)
            m.mark_stale(kind="offer", room="r2", keep=set())
            self.assertEqual(m.compact(keep_stale=2), 2 + 3)
            texts = {t for (t,) in m.db.execute("SELECT text FROM facts")}
            self.assertIn("Salvage Cache holds 12 materials available to harvest.", texts)
            self.assertNotIn("Salvage Cache holds 10 materials available to harvest.", texts)
            self.assertIn("Relay Quarter offers HARVEST", texts)
            self.assertEqual(m.recall("Salvage Cache")[0]["fact"], "Salvage Cache holds 12 materials available to harvest.")
