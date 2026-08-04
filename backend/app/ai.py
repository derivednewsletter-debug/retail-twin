from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

from typing import Any, Optional

import httpx


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    url: str
    env_vars: tuple[str, ...]
    default_model: str
    kind: str


PROVIDERS: dict[str, ProviderConfig] = {
    "groq": ProviderConfig(
        "groq",
        "https://api.groq.com/openai/v1/chat/completions",
        ("GROQ_API_KEY", "EXPO_PUBLIC_GROQ_API_KEY"),
        "llama-3.3-70b-versatile",
        "openai",
    ),
    "openrouter": ProviderConfig(
        "openrouter",
        "https://openrouter.ai/api/v1/chat/completions",
        ("OPENROUTER_API_KEY", "EXPO_PUBLIC_OPENROUTER_API_KEY"),
        "meta-llama/llama-3.3-70b-instruct",
        "openai",
    ),
    "nvidia": ProviderConfig(
        "nvidia",
        "https://integrate.api.nvidia.com/v1/chat/completions",
        ("NVIDIA_NIM_API_KEY", "NVIDIA_API_KEY", "EXPO_PUBLIC_NVIDIA_NIM_API_KEY"),
        "meta/llama-3.3-70b-instruct",
        "openai",
    ),
    "gemini": ProviderConfig(
        "gemini",
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        ("GEMINI_API_KEY", "EXPO_PUBLIC_GEMINI_API_KEY"),
        "gemini-2.5-flash",
        "gemini",
    ),
    "cohere": ProviderConfig(
        "cohere",
        "https://api.cohere.com/v2/chat",
        ("COHERE_API_KEY", "EXPO_PUBLIC_COHERE_API_KEY"),
        "command-r-plus",
        "cohere",
    ),
}

PROVIDER_ORDER = ("nvidia", "groq", "openrouter", "gemini", "cohere")


@dataclass
class AIResult:
    provider: str
    model: str
    content: str
    used_fallback: bool
    error: Optional[str] = None


class AIService:
    def __init__(self, timeout_seconds: float = 12.0, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.timeout = httpx.Timeout(timeout_seconds, connect=5.0)
        self.transport = transport

    def _api_key(self, config: ProviderConfig) -> str | None:
        for env_var in config.env_vars:
            value = os.getenv(env_var, "").strip()
            if value:
                return value
        return None

    def status(self) -> dict[str, Any]:
        providers = []
        for name, config in PROVIDERS.items():
            providers.append({
                "name": name,
                "configured": bool(self._api_key(config)),
                "model": config.default_model,
            })
        return {"providers": providers, "fallback": "deterministic simulation copy", "mode": "ai-enabled" if any(item["configured"] for item in providers) else "deterministic"}

    async def generate(self, prompt: str, provider: str = "auto", model: Optional[str] = None) -> AIResult:
        candidates = list(PROVIDER_ORDER) if provider == "auto" else [provider]
        last_error: Optional[str] = None
        for name in candidates:
            config = PROVIDERS.get(name)
            if config is None:
                last_error = f"Unknown provider: {name}"
                continue
            api_key = self._api_key(config)
            if not api_key:
                continue
            try:
                selected_model = model or config.default_model
                content = await self._call(config, api_key, selected_model, prompt)
                if content.strip():
                    return AIResult(name, selected_model, content.strip(), False)
                last_error = f"{name} returned an empty response"
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
                last_error = f"{name}: {exc}"
        return AIResult("deterministic", "seeded-local", self._fallback(prompt), True, last_error)

    async def _call(self, config: ProviderConfig, api_key: str, model: str, prompt: str) -> str:
        headers = {"Content-Type": "application/json"}
        if config.kind in {"openai", "cohere"}:
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers["x-goog-api-key"] = api_key

        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            if config.kind == "openai":
                request_headers = headers.copy()
                if config.name == "openrouter":
                    request_headers.update({
                        "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://retail-twin.vercel.app"),
                        "X-Title": "Retail Twin",
                    })
                response = await client.post(
                    config.url,
                    headers=request_headers,
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": "You are a concise retail location strategy analyst. Return practical executive insight."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.35,
                        "max_tokens": 700,
                    },
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]

            if config.kind == "gemini":
                response = await client.post(
                    config.url.format(model=model),
                    headers=headers,
                    json={"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.35, "maxOutputTokens": 700}},
                )
                response.raise_for_status()
                return response.json()["candidates"][0]["content"]["parts"][0]["text"]

            response = await client.post(
                config.url,
                headers=headers,
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a concise retail location strategy analyst. Return practical executive insight."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.35,
                    "max_tokens": 700,
                },
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            if isinstance(content, list):
                return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
            return str(content)

    def _fallback(self, prompt: str) -> str:
        if "Location B" in prompt or "Broadway Subway" in prompt:
            return "Location B wins because the subway exit creates a natural pause point: fewer raw passersby, stronger conversion, and more repeat visits. Protect the morning commute window, staff for the lunch surge, and use the first campaign to build a habit with nearby office workers."
        return "The strongest opportunity is the location with the clearest customer routine, not necessarily the most impressions. Prioritize repeat behavior, conversion context, and operating-hour demand before committing capital."


ai_service = AIService()
