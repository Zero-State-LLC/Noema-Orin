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


class CloudDecideTests(unittest.TestCase):
    ENV = {"MEMORY_SYNC_URL": "https://w", "MEMORY_SYNC_TOKEN": "t"}

    def _adapter(self):
        from noema_orin.health import WorkersAICircuitBreaker
        a = orin_adapter.OrinAdapter.__new__(orin_adapter.OrinAdapter)
        a.model, a.num_ctx, a.timeout, a.base_url = "m", 4096, 1, "http://127.0.0.1:9/v1"
        a.breaker = WorkersAICircuitBreaker(failure_threshold=2, cooldown_seconds=60)
        return a

    def test_breaker_opens_and_skips_remote(self):
        a = self._adapter()
        with mock.patch.dict("os.environ", {**self.ENV, "NOEMA_DECIDE_LOCAL_FALLBACK": "0"}), \
                mock.patch("urllib.request.urlopen", side_effect=OSError) as u:
            for _ in range(4):
                a._chat("s", "u")
        self.assertEqual(u.call_count, 2)  # two failures open the breaker; later turns skip the network

    def test_chat_uses_cloud_route(self):
        body = json.dumps({"text": '{"choice": 1, "why": "role verb"}'}).encode()
        with mock.patch.dict("os.environ", self.ENV), mock.patch("urllib.request.urlopen", return_value=_Resp(body)) as u:
            self.assertEqual(self._adapter()._chat("s", "u", num_predict=60), {"choice": 1, "why": "role verb"})
        self.assertTrue(u.call_args[0][0].full_url.endswith("/chat"))

    def test_chat_can_refuse_local_fallback(self):
        with mock.patch.dict("os.environ", {**self.ENV, "NOEMA_DECIDE_LOCAL_FALLBACK": "0"}), \
                mock.patch("urllib.request.urlopen", side_effect=OSError):
            self.assertEqual(self._adapter()._chat("s", "u"), {})

    def test_last_resort_uses_openai_route_not_ollama(self):
        """D-090: the last local fallback goes to llama-server's /v1/chat/completions, never Ollama /api/chat.

        llama-server answers /api/chat with 404, so the old path only worked while Ollama ran.
        """
        body = json.dumps({"choices": [{"message": {"content": '{"choice": 2}'}}]}).encode()
        a = self._adapter()
        a.base_url = "http://127.0.0.1:8081/v1"
        env = {k: v for k, v in self.ENV.items()}
        env.pop("MEMORY_SYNC_URL")
        with mock.patch.dict("os.environ", env, clear=True), \
                mock.patch("urllib.request.urlopen", return_value=_Resp(body)) as u:
            self.assertEqual(a._chat("s", "u", num_predict=60), {"choice": 2})
        urls = [c[0][0].full_url for c in u.call_args_list]
        self.assertTrue(urls, "a local call was made")
        self.assertTrue(all(url.endswith("/v1/chat/completions") for url in urls), urls)
        self.assertFalse(any("/api/chat" in url for url in urls))

    def test_default_base_is_llama_server(self):
        from importlib.util import find_spec
        if not find_spec("noema_client"):
            self.skipTest("needs noema-client")
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(orin_adapter.from_env("brief").base_url, "http://127.0.0.1:8081/v1")


if __name__ == "__main__":
    unittest.main()
