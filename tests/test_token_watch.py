import base64
import json
import tempfile
import unittest
from pathlib import Path

from noema_orin.token_watch import check


def jwt(claims):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{enc({'alg': 'none'})}.{enc(claims)}.sig"


class TokenWatchTests(unittest.TestCase):
    def test_statuses_and_no_token_in_output(self):
        now = 1_800_000_000
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "a.env").write_text(f"NOEMA_TOKEN={jwt({'sub': 'player.A', 'exp': now + 20 * 86400})}\nNOEMA_SERVER=x\n")
            (p / "b.env").write_text(f"NOEMA_TOKEN={jwt({'sub': 'player.B', 'exp': now + 3 * 86400})}\n")
            (p / "c.env").write_text(f"NOEMA_TOKEN={jwt({'sub': 'player.C', 'exp': now - 10})}\n")
            (p / "memory-sync.env").write_text("MEMORY_SYNC_TOKEN=abc\n")
            code, rows = check(p, 7, now=now)
        self.assertEqual(code, 2)
        self.assertEqual([r["status"] for r in rows], ["OK", "WARN", "EXPIRED"])
        self.assertNotIn("sig", json.dumps(rows))


if __name__ == "__main__":
    unittest.main()
