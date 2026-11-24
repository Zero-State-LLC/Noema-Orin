import unittest

from noema_orin import ws


class _Closing:
    def send(self, data):
        from websockets.exceptions import ConnectionClosedError
        raise ConnectionClosedError(None, None)

    def recv(self):
        return "{}"

    def close(self):
        raise RuntimeError("already closed")


@unittest.skipUnless(__import__("importlib").util.find_spec("websockets"), "needs websockets")
class WsTests(unittest.TestCase):
    def test_connection_closed_becomes_connection_error(self):
        sock = ws._Socket(_Closing())
        with self.assertRaises(ConnectionError):
            sock.send("x")
        self.assertEqual(sock.recv(), "{}")
        self.assertIsNone(sock.close())


if __name__ == "__main__":
    unittest.main()
