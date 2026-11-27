import contextlib
import gc
import json
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

from noema_orin import memory_sync
from noema_orin.memory import Memory, WorldMap


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        with Memory(self.root / "m01" / "mind") as mem:
            mem.remember("Civic offers HARVEST", kind="offer", room="room.civic", sequence=5)
        (self.root / "m01" / "mind" / "persona.json").write_text(json.dumps({"name": "Aphelia", "version": 3}))
        with WorldMap(self.root) as wm:
            wm.observe("room.civic", "Civic", 5, ["room.ring"], ["HARVEST"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_incremental_and_marks_only_after_success(self):
        calls = []
        with mock.patch.dict("os.environ", {"MEMORY_SYNC_URL": "https://x", "MEMORY_SYNC_TOKEN": "t"}), \
                mock.patch.object(memory_sync, "post", side_effect=lambda u, t, p: calls.append(p) or {"written": 1}):
            memory_sync.main(["--root", str(self.root)])
            self.assertEqual({c["member"] for c in calls}, {"m01", "_map"})
            self.assertTrue(all(not k.startswith("_") for c in calls for k in c))
            calls.clear()
            memory_sync.main(["--root", str(self.root)])
            self.assertEqual(calls, [])

    def test_failure_keeps_rows_for_retry(self):
        with mock.patch.dict("os.environ", {"MEMORY_SYNC_URL": "https://x", "MEMORY_SYNC_TOKEN": "t"}), \
                mock.patch.object(memory_sync, "post", side_effect=OSError):
            memory_sync.main(["--root", str(self.root)])
        payload = memory_sync.collect(self.root, "m01", json.loads((self.root / "shared" / "sync-marks.json").read_text()))
        self.assertEqual(len(payload["facts"]), 1)

    def test_metrics_sessions_and_digest_sync_once(self):
        from noema_orin.metrics import open_db
        with contextlib.closing(open_db(self.root)) as db:
            db.execute("INSERT INTO sessions VALUES ('a.log',1,1.0,'m01','founder',3,'duration_elapsed',NULL,1,1,3,0,'{}')")
            db.commit()
        (self.root / "shared" / "digest.json").write_text('{"alerts": []}')
        calls = []
        with mock.patch.dict("os.environ", {"MEMORY_SYNC_URL": "https://x", "MEMORY_SYNC_TOKEN": "t"}), \
                mock.patch.object(memory_sync, "post", side_effect=lambda u, t, p: calls.append(p) or {"written": 1}):
            memory_sync.main(["--root", str(self.root)])
            metrics = [c for c in calls if c["member"] == "_metrics"]
            self.assertEqual(len(metrics[0]["sessions"]), 1)
            self.assertEqual(metrics[0]["digest"], {"alerts": []})
            calls.clear()
            memory_sync.main(["--root", str(self.root)])
            self.assertEqual([c for c in calls if c["member"] == "_metrics"], [])

    def test_unconfigured_is_a_noop(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(memory_sync.main(["--root", str(self.root)]), 0)

    def test_collect_closes_sqlite_handles(self):
        from noema_orin.metrics import open_db
        with contextlib.closing(open_db(self.root)) as db:
            db.commit()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            for member in ("m01", "_metrics", "_map"):
                memory_sync.collect(self.root, member, {})
            gc.collect()
        resource_warnings = [w for w in caught if issubclass(w.category, ResourceWarning)]
        self.assertEqual(resource_warnings, [])


if __name__ == "__main__":
    unittest.main()
