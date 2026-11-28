import gzip
import os
import tempfile
import unittest
from pathlib import Path

from noema_orin.logrotate import rotate, rotate_dir


class LogRotateTests(unittest.TestCase):
    """D-089: the unit logs grow without bound (no logrotate on the Orin)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _log(self, name, size):
        p = self.root / name
        p.write_bytes(b"x" * (size - 1) + b"\n")
        return p

    def test_small_log_is_left_alone(self):
        p = self._log("noema-player@m01.log", 100)
        self.assertFalse(rotate(p, max_bytes=1000, keep=3))
        self.assertEqual(p.stat().st_size, 100)
        self.assertEqual(sorted(x.name for x in self.root.iterdir()), ["noema-player@m01.log"])

    def test_large_log_is_compressed_and_truncated_in_place(self):
        p = self._log("noema-player@m01.log", 2000)
        inode = p.stat().st_ino
        self.assertTrue(rotate(p, max_bytes=1000, keep=3))
        self.assertEqual(p.stat().st_size, 0)
        self.assertEqual(p.stat().st_ino, inode, "the unit's open descriptor must keep pointing at the live file")
        with gzip.open(self.root / "noema-player@m01.log.1.gz", "rb") as fh:
            self.assertEqual(len(fh.read()), 2000)

    def test_open_append_writer_keeps_writing_after_rotation(self):
        p = self._log("noema-player@m02.log", 2000)
        fd = os.open(p, os.O_WRONLY | os.O_APPEND)
        try:
            rotate(p, max_bytes=1000, keep=3)
            os.write(fd, b"next line\n")
        finally:
            os.close(fd)
        self.assertEqual(p.read_bytes(), b"next line\n")

    def test_keep_bounds_the_number_of_archives(self):
        p = self.root / "noema-player@m03.log"
        for i in range(5):
            p.write_bytes(bytes([65 + i]) * 2000)
            rotate(p, max_bytes=1000, keep=3)
        names = sorted(x.name for x in self.root.iterdir())
        self.assertEqual(names, ["noema-player@m03.log", "noema-player@m03.log.1.gz",
                                 "noema-player@m03.log.2.gz", "noema-player@m03.log.3.gz"])
        with gzip.open(self.root / "noema-player@m03.log.1.gz", "rb") as fh:
            self.assertEqual(fh.read()[:1], b"E", "newest archive is .1")

    def test_rotate_dir_only_touches_dot_log_files(self):
        self._log("metrics.log", 2000)
        (self.root / "noema-player@m01.log.1.gz").write_bytes(b"old")
        (self.root / "notes.txt").write_bytes(b"x" * 5000)
        self.assertEqual(rotate_dir(self.root, max_bytes=1000, keep=2), ["metrics.log"])
        self.assertEqual((self.root / "notes.txt").stat().st_size, 5000)

    def test_mode_is_preserved(self):
        p = self._log("token-watch.log", 2000)
        os.chmod(p, 0o640)
        rotate(p, max_bytes=1000, keep=2)
        self.assertEqual((self.root / "token-watch.log.1.gz").stat().st_mode & 0o777, 0o640)


if __name__ == "__main__":
    unittest.main()
