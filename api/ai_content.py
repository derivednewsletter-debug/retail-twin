from __future__ import annotations

import asyncio
import json
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx


# ---------------------------------------------------------------------------
# AI Content Generator — generates realistic consumer posts and competitor events
# using all 5 configured providers with automatic fallback
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderConfig:
    name: str
    url: str
    env_vars: tuple[str, ...]
    default_model: str
    kind: str  # "openai", "gemini", "cohere"


PROVIDERS: dict[str, ProviderConfig] = {
    "groq": ProviderConfig(
        "groq", "https://api.groq.com/openai/v1/chat/completions",
        ("GROQ_API_KEY", "EXPO_PUBLIC_GROQ_API_KEY"),
        "llama-3.3-70b-versatile", "openai",
    ),
    "openrouter": ProviderConfig(
        "openrouter", "https://openrouter.ai/api/v1/chat/completions",
        ("OPENROUTER_API_KEY", "EXPO_PUBLIC_OPENROUTER_API_KEY"),
        "meta-llama/llama-3.3-70b-instruct", "openai",
    ),
    "nvidia": ProviderConfig(
        "nvidia", "https://integrate.api.nvidia.com/v1/chat/completions",
        ("NVIDIA_NIM_API_KEY", "NVIDIA_API_KEY", "EXPO_PUBLIC_NVIDIA_NIM_API_KEY"),
        "meta/llama-3.3-70b-instruct", "openai",
    ),
    "gemini": ProviderConfig(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        ("GEMINI_API_KEY", "EXPO_PUBLIC_GEMINI_API_KEY"),
        "gemini-2.5-flash", "gemini",
    ),
    "cohere": ProviderConfig(
        "cohere", "https://api.cohere.com/v2/chat",
        ("COHERE_API_KEY", "EXPO_PUBLIC_COHERE_API_KEY"),
        "command-r-plus", "cohere",
    ),
}

# Provider preference order for content generation (speed + quality)
CONTENT_PROVIDER_ORDER = ("groq", "nvidia", "openrouter", "gemini", "cohere")


def _get_api_key(config: ProviderConfig) -> Optional[str]:
    for env_var in config.env_vars:
        value = os.getenv(env_var, "").strip()
        if value:
            return value
    return None


@dataclass
class ContentResult:
    provider: str
    model: str
    used_fallback: bool


class AIContentGenerator:
    """Generates consumer posts, competitor events, and insights using AI providers."""

    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self.timeout = httpx.Timeout(timeout_seconds, connect=4.0)
        self._content_cache: dict[str, Any] = {}
        self._last_generate: float = 0
        self._min_interval: float = 2.0  # Don't generate faster than every 2 seconds

    def available_providers(self) -> list[str]:
        return [name for name, config in PROVIDERS.items() if _get_api_key(config)]

    async def generate_consumer_posts(
        self, brand: str, category: str, weather_condition: str,
        hour: int, location_name: str, sentiment_bias: str = "mixed",
    ) -> list[dict[str, Any]]:
        """Generate 2-3 realistic consumer social media posts about visiting the store."""
        now = time.time()
        if now - self._last_generate < self._min_interval:
            return []  # Rate-limit content generation
        self._last_generate = now

        time_context = "morning commute" if hour < 10 else "lunch rush" if hour < 14 else "afternoon" if hour < 17 else "evening"
        weather_context = f" on a {weather_condition} day" if weather_condition not in ("clear", "overcast") else ""

        prompt = f"""Generate exactly 2 short social media posts (like Instagram or Twitter) from different people about visiting "{brand}" (a {category.lower()} store) at {location_name} in SoHo, Manhattan{weather_context} during {time_context}.

Context:
- The store just opened recently
- Location is in SoHo, a trendy NYC neighborhood
- {sentiment_bias} sentiment overall

Return ONLY a JSON array with exactly 2 objects, each with:
- "name": first name + last initial (e.g. "Sarah M.")
- "text": the post text (1-2 sentences, casual tone, under 280 chars)
- "sentiment": one of "positive", "neutral", or "negative"
- "archetype": one of "office", "local", "tourist", "resident"

Example format:
[{{"name":"Alex T.","text":"...","sentiment":"positive","archetype":"office"}}]"""

        result = await self._call_ai(prompt)
        if result:
            try:
                # Try to parse JSON from the response
                text = result.strip()
                # Find JSON array in the response
                start = text.find("[")
                end = text.rfind("]") + 1
                if start >= 0 and end > start:
                    posts = json.loads(text[start:end])
                    if isinstance(posts, list):
                        return posts[:3]
            except (json.JSONDecodeError, IndexError):
                pass
        return []

    async def generate_competitor_event(
        self, brand: str, competitors: list[str], hour: int,
        weather_condition: str,
    ) -> dict[str, Any]:
        """Generate a realistic competitor response event."""
        now = time.time()
        if now - self._last_generate < self._min_interval:
            return {}
        self._last_generate = now

        comp_names = ", ".join(competitors[:4])
        prompt = f"""Generate exactly 1 realistic competitor response event in a JSON object.

Context: "{brand}" is a new {brand.lower()} store in SoHo, Manhattan. Existing competitors in the area include: {comp_names}.

The competitor should react naturally to the new store opening. Generate ONE event.

Return ONLY a JSON object with:
- "competitor": the competitor name (use one from: {comp_names})
- "text": what they did (1 sentence, specific action like "launched a 10% discount", "extended hours", "increased social media spend")
- "kind": one of "discount", "hours", "ads", "operations", "renovation"

Example:
{{"competitor":"Blue Bottle","text":"launched a loyalty program targeting nearby office workers","kind":"operations"}}"""

        result = await self._call_ai(prompt)
        if result:
            try:
                text = result.strip()
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                    event = json.loads(text[start:end])
                    if isinstance(event, dict) and "competitor" in event:
                        return event
            except (json.JSONDecodeError, IndexError):
                pass
        return {}

    async def generate_executive_brief(
        self, brand: str, best_location: str, best_name: str,
        metrics: dict[str, Any], context_summary: str,
    ) -> str:
        """Generate an AI-powered executive brief for the report."""
        prompt = f"""You are a senior retail strategy consultant. Write a concise executive brief (3-4 sentences) recommending "{brand}" open at {best_name} (Location {best_location}) in SoHo, Manhattan.

Key metrics:
- Daily revenue: ${metrics.get('daily_revenue', 0):,}
- Annual revenue: ${metrics.get('annual_revenue', 0):,}
- Conversion rate: {metrics.get('conversion_rate', 0)}%
- Repeat rate: {metrics.get('repeat_rate', 0) * 100:.0f}%
- Foot traffic: {metrics.get('foot_traffic', 0):,}
- Payback period: {metrics.get('payback_months', 0)} months

Context: {context_summary}

Write in a confident, data-driven tone. Name one specific risk and one specific opportunity."""

        result = await self._call_ai(prompt)
        return result if result else (
            f"Location {best_location} ({best_name}) is the recommended site for {brand}. "
            f"With projected daily revenue of ${metrics.get('daily_revenue', 0):,} and a {metrics.get('conversion_rate', 0)}% conversion rate, "
            f"this location offers the strongest balance of foot traffic and customer intent. "
            f"The key opportunity is building repeat habits with nearby office workers; "
            f"the main risk is strong existing competitor loyalty within a 2-block radius."
        )

    async def _call_ai(self, prompt: str) -> Optional[str]:
        """Try all configured providers in order, return first successful result."""
        for name in CONTENT_PROVIDER_ORDER:
            config = PROVIDERS.get(name)
            if config is None:
                continue
            api_key = _get_api_key(config)
            if not api_key:
                continue
            try:
                content = await self._provider_call(config, api_key, prompt)
                if content and content.strip():
                    return content.strip()
            except Exception:
                continue
        return None

    async def _provider_call(
        self, config: ProviderConfig, api_key: str, prompt: str,
    ) -> Optional[str]:
        """Make a single API call to a provider."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.kind in ("openai", "cohere"):
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers["x-goog-api-key"] = api_key

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if config.kind == "openai":
                request_headers = headers.copy()
                if config.name == "openrouter":
                    request_headers["HTTP-Referer"] = "https://retail-twin.vercel.app"
                    request_headers["X-Title"] = "Retail Twin"
                resp = await client.post(
                    config.url, headers=request_headers,
                    json={
                        "model": config.default_model,
                        "messages": [
                            {"role": "system", "content": "You are a realistic NYC consumer or retail analyst. Return only the requested JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.8,
                        "max_tokens": 400,
                    },
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]

            if config.kind == "gemini":
                resp = await client.post(
                    config.url.format(model=config.default_model),
                    headers=headers,
                    json={
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.8, "maxOutputTokens": 400},
                    },
                )
                resp.raise_for_status()
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

            # Cohere
            resp = await client.post(
                config.url, headers=headers,
                json={
                    "model": config.default_model,
                    "message": prompt,
                    "temperature": 0.8,
                    "max_tokens": 400,
                },
            )
            resp.raise_for_status()
            msg = resp.json().get("message", {})
            content = msg.get("content", "")
            if isinstance(content, list):
                return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
            return str(content)
