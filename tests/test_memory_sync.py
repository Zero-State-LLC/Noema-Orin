import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from noema_orin import memory_sync
from noema_orin.memory import Memory, WorldMap


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        Memory(self.root / "m01" / "mind").remember("Civic offers HARVEST", kind="offer", room="room.civic", sequence=5)
        (self.root / "m01" / "mind" / "persona.json").write_text(json.dumps({"name": "Aphelia", "version": 3}))
        WorldMap(self.root).observe("room.civic", "Civic", 5, ["room.ring"], ["HARVEST"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_incremental_and_marks_only_after_success(self):
        calls = []
        with mock.patch.dict("os.environ", {"MEMORY_SYNC_URL": "https://x", "MEMORY_SYNC_TOKEN": "t"}), \
                mock.patch.object(memory_sync, "post", side_effect=lambda u, t, p: calls.append(p) or {"written": 1}):
            memory_sync.main(["--root", str(self.root)])
            self.assertEqual({c["member"] for c in calls}, {"m01", "_map"})
            calls.clear()
            memory_sync.main(["--root", str(self.root)])
            self.assertEqual(calls, [])

    def test_failure_keeps_rows_for_retry(self):
        with mock.patch.dict("os.environ", {"MEMORY_SYNC_URL": "https://x", "MEMORY_SYNC_TOKEN": "t"}), \
                mock.patch.object(memory_sync, "post", side_effect=OSError):
            memory_sync.main(["--root", str(self.root)])
        payload = memory_sync.collect(self.root, "m01", json.loads((self.root / "shared" / "sync-marks.json").read_text()))
        self.assertEqual(len(payload["facts"]), 1)

    def test_unconfigured_is_a_noop(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(memory_sync.main(["--root", str(self.root)]), 0)


if __name__ == "__main__":
    unittest.main()
