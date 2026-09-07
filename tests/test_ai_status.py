import asyncio
import json
import time
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.ai import AIClient, AIResponseError
from app.ai_errors import AIServiceError, provider_error


def http_error(status, *, metadata=None, headers=None, message="Sensitive provider text"):
    response = httpx.Response(status, headers=headers, json={"error": {"message": message, "metadata": metadata or {}}, "user_id": "PRIVATE_ACCOUNT"},
                              request=httpx.Request("POST", "https://example.test/chat/completions"))
    return httpx.HTTPStatusError("Private raw body", request=response.request, response=response)


class ProviderErrorTests(unittest.TestCase):
    def test_daily_quota_metadata_and_millisecond_reset_are_parsed_without_account_details(self):
        error = provider_error(http_error(429, metadata={"limit_source": "openrouter_free_tier_daily", "headers": {
            "X-RateLimit-Limit": "50", "X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1788566400000"}}), "analysis")
        self.assertEqual(error.status_code, 429)
        self.assertEqual(error.payload["error_code"], "AI_DAILY_QUOTA_EXCEEDED")
        self.assertEqual(error.payload["quota_limit"], 50)
        self.assertEqual(error.payload["quota_remaining"], 0)
        self.assertEqual(error.payload["retry_at"], "2026-09-05T00:00:00+00:00")
        self.assertNotIn("PRIVATE", json.dumps(error.payload))
        self.assertNotIn("Sensitive", str(error))

    def test_temporary_rate_limit_is_not_labelled_daily_quota(self):
        error = provider_error(http_error(429, headers={"Retry-After": "30"}), "rerank")
        self.assertEqual(error.payload["error_code"], "AI_RATE_LIMITED")
        self.assertIsNotNone(error.payload["retry_at"])

    def test_malformed_headers_and_html_bodies_are_safe(self):
        error = provider_error(http_error(429, headers={"X-RateLimit-Reset": "nan", "X-RateLimit-Limit": "unknown"}), "analysis")
        self.assertIsNone(error.payload["retry_at"])
        self.assertIsNone(error.payload["quota_limit"])
        response = httpx.Response(502, text="Private upstream traceback", request=httpx.Request("POST", "https://example.test"))
        error = provider_error(httpx.HTTPStatusError("bad", request=response.request, response=response), "analysis")
        self.assertNotIn("traceback", str(error))

    def test_credit_auth_network_and_timeout_have_distinct_codes(self):
        for status, code in ((402, "AI_CREDIT_REQUIRED"), (401, "AI_AUTH_ERROR"), (403, "AI_AUTH_ERROR"), (503, "AI_PROVIDER_ERROR")):
            self.assertEqual(provider_error(http_error(status), "analysis").payload["error_code"], code)
        self.assertEqual(provider_error(httpx.ConnectError("network"), "analysis").payload["error_code"], "AI_PROVIDER_UNAVAILABLE")
        self.assertEqual(provider_error(httpx.ReadTimeout("timeout"), "analysis").payload["error_code"], "AI_TIMEOUT")


class HealthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ai = AIClient()
        self.ai.api_key = "test-only"
        self.ai.chat_json = AsyncMock(return_value={"connected": True})
        self.ai.embed = AsyncMock(return_value=[[1.0]])
        self.ai.rerank = AsyncMock(return_value=[{"index": 0, "relevance_score": 1}])

    async def test_all_three_components_are_checked_and_reloads_reuse_cache(self):
        first, second = await asyncio.gather(self.ai.healthcheck(), self.ai.healthcheck())
        self.assertEqual(first["ai_status"], "connected")
        self.assertEqual(first, second)
        for operation in (self.ai.chat_json, self.ai.embed, self.ai.rerank):
            operation.assert_awaited_once()

    async def test_embedding_success_cannot_hide_exhausted_analysis_quota(self):
        self.ai.chat_json.side_effect = provider_error(http_error(429, metadata={"limit_source": "openrouter_free_tier_daily"}), "analysis")
        report = await self.ai.healthcheck()
        self.assertEqual(report["ai_status"], "quota")
        self.assertEqual(report["components"], {"analysis": "error", "embedding": "connected", "rerank": "connected"})
        await self.ai.healthcheck()
        self.ai.chat_json.assert_awaited_once()

    async def test_real_failure_invalidates_previously_green_health(self):
        await self.ai.healthcheck()
        self.ai.remember_failure(provider_error(http_error(402), "analysis"))
        self.assertEqual((await self.ai.healthcheck())["ai_status"], "credit")

    async def test_concurrent_request_failure_cannot_be_overwritten_by_green_probe(self):
        async def classify(*args, **kwargs):
            self.ai.remember_failure(provider_error(http_error(429), "analysis"))
            return {"connected": True}
        self.ai.chat_json.side_effect = classify
        self.assertEqual((await self.ai.healthcheck())["ai_status"], "quota")

    async def test_manual_refresh_or_cache_expiry_can_recover(self):
        self.ai.remember_failure(provider_error(http_error(429), "analysis"))
        self.assertEqual((await self.ai.healthcheck(force=True))["ai_status"], "connected")
        self.ai.remember_failure(provider_error(http_error(429), "analysis"))
        self.ai._health_until = time.monotonic() - 1
        self.assertEqual((await self.ai.healthcheck())["ai_status"], "connected")

    async def test_invalid_analysis_response_does_not_show_connected(self):
        self.ai.chat_json.side_effect = AIResponseError("Invalid")
        self.assertEqual((await self.ai.healthcheck())["ai_status"], "error")

    async def test_missing_key_makes_no_provider_calls(self):
        self.ai.api_key = ""
        self.assertEqual((await self.ai.healthcheck())["ai_status"], "off")
        self.ai.chat_json.assert_not_awaited()


class ProviderTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_provider_response_remains_usable(self):
        ai = AIClient()
        ai.api_key = "test-only"
        response = httpx.Response(200, json={"choices": [{"message": {"content": '{"subcategory_id":"DATA.EXCEL","topic":"Excel","intent":"Training"}'}}]}, request=httpx.Request("POST", "https://example.test"))
        with patch("app.ai.httpx.AsyncClient") as client:
            client.return_value.__aenter__.return_value.post = AsyncMock(return_value=response)
            result = await ai.classify_request("Synthetic training need")
        self.assertEqual(result["subcategory_id"], "DATA.EXCEL")
        self.assertEqual(result["topic"], "Excel")

    async def test_http_200_error_envelope_is_treated_as_quota_failure(self):
        ai = AIClient()
        ai.api_key = "test-only"
        response = httpx.Response(200, json={"error": {"code": 429, "message": "free-models-per-day"}}, request=httpx.Request("POST", "https://example.test"))
        with patch("app.ai.httpx.AsyncClient") as client:
            client.return_value.__aenter__.return_value.post = AsyncMock(return_value=response)
            with self.assertRaises(AIServiceError) as raised:
                await ai.chat_json("system", "user")
        self.assertEqual(raised.exception.payload["error_code"], "AI_DAILY_QUOTA_EXCEEDED")
        self.assertEqual((await ai.healthcheck())["ai_status"], "quota")
