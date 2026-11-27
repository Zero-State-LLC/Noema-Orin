"""S15 cost alarm, S17 map compaction."""
import contextlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from noema_orin import metrics
from noema_orin.memory import WorldMap
from noema_orin.memory_sync import compact_map


def session(calls, fb):
    return json.dumps({"member": "m02", "role": "quartermaster", "actions": 1, "stop_reason": "duration_elapsed",
                       "health": {"workers_ai_calls": calls, "ollama_fallbacks": fb}})


class CostAlarmTests(unittest.TestCase):
    def test_deltas_from_cumulative_counters_and_alarms(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "logs").mkdir()
        log = root / "logs" / "noema-player@m02.log"
        log.write_text("\n".join([session(100, 2), session(250, 30)]) + "\n")
        with contextlib.closing(metrics.open_db(root)) as db:
            metrics.collect(root, db)
            self.assertEqual(db.execute("SELECT sum(calls), sum(fallbacks) FROM cost").fetchone(), (250, 30))
            alerts = metrics.cost_alerts(db, 24)
            self.assertTrue(any("fallbacks 30/250" in a for a in alerts), alerts)
            self.assertFalse(any("model calls" in a for a in alerts))
            self.assertTrue(any("model calls" in a for a in metrics.cost_alerts(db, 0.5)))  # 250 >= 0.7*10000/48


class CompactMapTests(unittest.TestCase):
    def test_drops_old_work_and_truncates_wal(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with WorldMap(Path(tmp.name)) as m:
            m.record_work("p", "room.a", [("REPAIR", "e", "")], 1)
            m.record_work("p", "room.b", [("REPAIR", "e", "")], 30_000)
        out = compact_map(Path(tmp.name) / "shared" / "map.db")
        self.assertEqual(out["work_dropped"], 1)
        with contextlib.closing(sqlite3.connect(Path(tmp.name) / "shared" / "map.db")) as db:
            rows = db.execute("SELECT room_id FROM work").fetchall()
        self.assertEqual(rows, [("room.b",)])


if __name__ == "__main__":
    unittest.main()
