import asyncio
import json

import httpx

from app.ai import AIService


def test_missing_keys_use_deterministic_fallback(monkeypatch):
    for name in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY", "NVIDIA_NIM_API_KEY", "COHERE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    result = asyncio.run(AIService().generate("Compare Location A and Location B for a coffee store."))
    assert result.provider == "deterministic"
    assert result.used_fallback is True
    assert "Location B" in result.content


def test_groq_payload_and_response_are_normalized():
    seen = {}

    async def handler(request: httpx.Request):
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Use the subway exit."}}]})

    async def run():
        transport = httpx.MockTransport(handler)
        service = AIService(transport=transport)
        original = service._api_key
        service._api_key = lambda _: "test-key"
        try:
            return await service.generate("Choose a location", provider="groq")
        finally:
            service._api_key = original

    result = asyncio.run(run())
    assert result.provider == "groq"
    assert result.content == "Use the subway exit."
    assert seen["headers"]["authorization"] == "Bearer test-key"
    assert seen["body"]["messages"][-1]["content"] == "Choose a location"


def test_gemini_payload_and_response_are_normalized():
    seen = {}

    async def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Gemini recommendation"}]}}]})

    async def run():
        service = AIService(transport=httpx.MockTransport(handler))
        service._api_key = lambda _: "gemini-test"
        return await service.generate("Explain the conversion gap", provider="gemini")

    result = asyncio.run(run())
    assert result.provider == "gemini"
    assert result.content == "Gemini recommendation"
    assert "gemini-2.5-flash:generateContent" in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == "gemini-test"
    assert seen["body"]["contents"][0]["parts"][0]["text"] == "Explain the conversion gap"
