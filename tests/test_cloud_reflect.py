import io
import json
import unittest
from unittest import mock

from noema_orin import orin_adapter


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class CloudReflectTests(unittest.TestCase):
    ENV = {"MEMORY_SYNC_URL": "https://w", "MEMORY_SYNC_TOKEN": "t"}

    def test_parses_json_from_model_text(self):
        body = json.dumps({"text": 'Sure: {"trait_deltas": {"caution": 0.05}, "lesson": "Seat allies."}'}).encode()
        with mock.patch.dict("os.environ", self.ENV), mock.patch("urllib.request.urlopen", return_value=_Resp(body)) as u:
            out = orin_adapter._cloud_reflect("s", "u")
        self.assertEqual(out["lesson"], "Seat allies.")
        self.assertTrue(u.call_args[0][0].full_url.endswith("/reflect"))

    def test_unreachable_returns_none_and_no_local_by_default(self):
        adapter = mock.Mock()
        persona = {"name": "A", "role": "founder", "traits": {}, "quirk": "", "lessons": []}
        with mock.patch.dict("os.environ", self.ENV), mock.patch("urllib.request.urlopen", side_effect=OSError):
            self.assertIsNone(orin_adapter.reflect(adapter, persona, []))
        adapter._chat.assert_not_called()

    def test_unconfigured_returns_none(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(orin_adapter._cloud_reflect("s", "u"))


if __name__ == "__main__":
    unittest.main()
