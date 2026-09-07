import asyncio
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch
import httpx

from app.ai import AIClient, _groq_retry_delay
from app.config import settings
from app.local_models import embedding_identity, model_path
from app.ai_errors import AIServiceError


class ProviderConfigTests(unittest.TestCase):
    def test_groq_selection_uses_only_groq_credential_and_endpoint(self):
        cfg = replace(settings, llm_provider="", groq_api_key="groq-test", openrouter_api_key="router-test")
        self.assertEqual(cfg.ai_mode, "groq")
        self.assertEqual(cfg.api_key, "groq-test")
        self.assertIn("api.groq.com", cfg.api_base_url)

    def test_explicit_provider_wins_and_missing_key_never_uses_another_provider_key(self):
        cfg = replace(settings, llm_provider="openrouter", groq_api_key="groq-test", openrouter_api_key="")
        self.assertEqual(cfg.ai_mode, "off")
        self.assertEqual(cfg.api_key, "")

    def test_bad_chunk_overlap_is_rejected(self):
        with self.assertRaises(ValueError):
            replace(settings, chunk_size=1000, chunk_overlap=1000)

    def test_settings_representation_does_not_expose_provider_secrets(self):
        cfg = replace(settings, groq_api_key="secret-groq-marker", openrouter_api_key="secret-router-marker")
        self.assertNotIn("secret-groq-marker", repr(cfg))
        self.assertNotIn("secret-router-marker", repr(cfg))

    def test_embedding_identity_changes_when_model_preprocessing_changes(self):
        with patch("app.local_models.settings", replace(settings, embedding_model="BAAI/bge-m3", local_max_tokens=512)):
            first = embedding_identity()
        with patch("app.local_models.settings", replace(settings, embedding_model="BAAI/bge-m3", local_max_tokens=1024)):
            self.assertNotEqual(first, embedding_identity())

    def test_unknown_model_cannot_download_or_execute_remote_code(self):
        with self.assertRaises(AIServiceError):
            model_path("arbitrary/unreviewed-model")

    def test_groq_retry_rejects_daily_quota_long_delay_and_invalid_headers(self):
        for status, headers, message in [
            (401, {"retry-after": "1"}, "auth"),
            (429, {"retry-after": "31"}, "short limit"),
            (429, {"retry-after": "nan"}, "short limit"),
            (429, {"retry-after": "-1"}, "short limit"),
            (429, {}, "short limit"),
            (429, {"retry-after": "1", "x-ratelimit-remaining-requests": "0"}, "daily"),
            (429, {"retry-after": "1"}, "Tokens per day limit"),
        ]:
            with self.subTest(status=status, headers=headers):
                response = httpx.Response(status, headers=headers, json={"error": {"message": message}})
                self.assertIsNone(_groq_retry_delay(response))


class ProviderRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_groq_short_rate_limit_is_retried_once_then_succeeds(self):
        cfg = replace(settings, llm_provider="groq", groq_api_key="test")
        request = httpx.Request("POST", "https://example.test")
        rate = httpx.Response(429, headers={"retry-after": "9"}, json={"error": {"message": "Tokens per minute limit"}}, request=request)
        success = httpx.Response(200, json={"ok": True}, request=request)
        with patch("app.ai.settings", cfg), patch("app.ai.httpx.AsyncClient") as transport, patch("app.ai.asyncio.sleep", new=AsyncMock()) as sleep:
            post = transport.return_value.__aenter__.return_value.post = AsyncMock(side_effect=[rate, success])
            client = AIClient()
            self.assertEqual(await client._post("chat/completions", {}, "analysis", 180), {"ok": True})
            self.assertEqual(post.await_count, 2)
            sleep.assert_awaited_once_with(9.5)
            self.assertIsNone(client._health_cache)

    async def test_groq_retry_is_bounded_and_second_failure_remains_visible(self):
        cfg = replace(settings, llm_provider="groq", groq_api_key="test")
        rate = httpx.Response(429, headers={"retry-after": "1"}, json={"error": {"message": "Tokens per minute limit"}}, request=httpx.Request("POST", "https://example.test"))
        with patch("app.ai.settings", cfg), patch("app.ai.httpx.AsyncClient") as transport, patch("app.ai.asyncio.sleep", new=AsyncMock()) as sleep:
            post = transport.return_value.__aenter__.return_value.post = AsyncMock(return_value=rate)
            client = AIClient()
            with self.assertRaises(AIServiceError):
                await client._post("chat/completions", {}, "analysis", 180)
            self.assertEqual(post.await_count, 2)
            sleep.assert_awaited_once()
            self.assertEqual(client._health_cache["ai_status"], "quota")

    async def test_remote_embedding_uses_its_own_key_not_the_groq_key(self):
        cfg = replace(settings, llm_provider="groq", groq_api_key="groq-test", openrouter_api_key="router-test", embedding_provider="openrouter")
        response = httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]}, request=httpx.Request("POST", "https://example.test"))
        with patch("app.ai.settings", cfg), patch("app.ai.httpx.AsyncClient") as transport:
            post = transport.return_value.__aenter__.return_value.post = AsyncMock(return_value=response)
            client = AIClient()
            await client.embed(["test"])
            self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer router-test")
            self.assertTrue(post.call_args.args[0].startswith(cfg.openrouter_base_url))

    async def test_local_embedding_never_calls_remote_api_or_adds_nvidia_prefix(self):
        cfg = replace(settings, embedding_provider="local")
        with patch("app.ai.settings", cfg), patch("app.ai.local_models.embed", new=AsyncMock(return_value=[[1.0]])) as embed:
            client = AIClient()
            client.api_key = ""
            with patch.object(client, "_post", new=AsyncMock()) as remote:
                self.assertEqual(await client.embed(["Turkish text"], is_query=True), [[1.0]])
                remote.assert_not_awaited()
            embed.assert_awaited_once_with(["Turkish text"])

    async def test_local_reranker_never_calls_groq(self):
        with patch("app.ai.settings", replace(settings, rerank_provider="local")), patch("app.ai.local_models.rerank", new=AsyncMock(return_value=[])) as rerank:
            client = AIClient()
            with patch.object(client, "_post", new=AsyncMock()) as remote:
                await client.rerank("query", ["doc"], 1)
                remote.assert_not_awaited()
            rerank.assert_awaited_once_with("query", ["doc"], 1)

    async def test_groq_payload_respects_reasoning_and_output_limits(self):
        cfg = replace(settings, llm_provider="groq", groq_api_key="test", llm_model="qwen/qwen3.8-27b", max_output_tokens=4096, primary_reasoning_effort="medium")
        with patch("app.ai.settings", cfg):
            client = AIClient()
            with patch.object(client, "_post", new=AsyncMock(return_value={"choices": [{"message": {"content": '{"ok":true}'}}]})) as post:
                await client.chat_json("system", "user")
                payload = post.call_args.args[1]
                self.assertEqual(payload["max_completion_tokens"], 4096)
                self.assertEqual(payload["reasoning_effort"], "medium")
                await client.chat_json("system", "user", max_tokens=256)
                self.assertEqual(post.call_args.args[1]["reasoning_effort"], "none")

    async def test_slow_local_work_does_not_block_server_event_loop(self):
        import time
        from app.local_models import LocalModelRuntime
        runtime = LocalModelRuntime()
        def slow(texts):
            time.sleep(0.1)
            return [[1.0]]
        with patch.object(runtime, "_embed", side_effect=slow):
            task = asyncio.create_task(runtime.embed(["test"]))
            await asyncio.sleep(0.01)
            self.assertFalse(task.done())
            self.assertEqual(await task, [[1.0]])
        runtime._executor.shutdown()
