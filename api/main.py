from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from pydantic import Literal

load_dotenv()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

Category = Literal[
    "Premium coffee",
    "Healthy fast casual",
    "Athletic apparel",
    "Fitness studio",
    "Beauty retail",
    "Specialty grocery",
]

MarketingChannel = Literal[
    "Grand opening",
    "Transit ads",
    "Local influencers",
    "Opening discount",
    "Social media",
]


class LocationConfig(BaseModel):
    id: Literal["A", "B", "C"]
    enabled: bool = True


class ScenarioConfig(BaseModel):
    category: Category = "Premium coffee"
    brand_name: str = Field(default="Northstar Coffee", min_length=2, max_length=60)
    average_ticket: float = Field(default=8.75, ge=1, le=200)
    store_size: int = Field(default=1400, ge=200, le=20000)
    opening_time: int = Field(default=7, ge=0, le=23)
    closing_time: int = Field(default=20, ge=1, le=24)
    marketing_budget: int = Field(default=85000, ge=0, le=5_000_000)
    positioning: str = Field(default="Thoughtful energy for the city", min_length=3, max_length=160)
    target_demographic: str = Field(default="Office workers + design-forward locals", min_length=3, max_length=120)
    locations: list[LocationConfig] = Field(default_factory=lambda: [LocationConfig(id="A"), LocationConfig(id="B"), LocationConfig(id="C")], min_length=1)
    marketing_channels: list[MarketingChannel] = Field(default_factory=lambda: ["Grand opening", "Transit ads"])

    @field_validator("closing_time")
    @classmethod
    def closing_after_opening(cls, value: int, info):
        opening = info.data.get("opening_time", 0)
        if value <= opening:
            raise ValueError("closing_time must be later than opening_time")
        return value

    @field_validator("locations")
    @classmethod
    def at_least_one_location(cls, value: list[LocationConfig]):
        if not any(location.enabled for location in value):
            raise ValueError("At least one location must be enabled")
        return value


class SimulationCommand(BaseModel):
    speed: Literal[1, 10, 100] = 10


class AIRequest(BaseModel):
    prompt: str = Field(min_length=8, max_length=5000)
    provider: Literal["auto", "groq", "openrouter", "gemini", "nvidia", "cohere"] = "auto"
    model: Optional[str] = Field(default=None, max_length=120)


class AIResponse(BaseModel):
    provider: str
    model: str
    content: str
    used_fallback: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Simulation engine
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DistrictLocation:
    id: str
    name: str
    x: float
    y: float
    rent: int
    traffic: int
    conversion: float
    context: str


DISTRICT_LOCATIONS = [
    DistrictLocation("A", "Spring & Mercer", 24, 31, 11800, 24500, 0.032, "high-volume commuter corridor"),
    DistrictLocation("B", "Broadway Subway", 72, 62, 9800, 14200, 0.068, "subway exit + office lobby dwell time"),
    DistrictLocation("C", "Prince Courtyard", 57, 82, 7900, 11800, 0.047, "weekend tourism + residential pocket"),
]

FEED_TEMPLATES = [
    ("Maya R.", "Walked past the new {brand} on my way to the studio — the line is already moving fast.", "positive"),
    ("Jordan L.", "The subway exit is the perfect spot for a quick {category} stop.", "positive"),
    ("Priya S.", "A little pricier than Blank Street, but the experience feels much more intentional.", "neutral"),
    ("Eli T.", "Honestly did not expect to become a regular this quickly. The staff remembers my order.", "positive"),
    ("Noah K.", "Lunch rush is intense today. Wonder if they will add more seating.", "neutral"),
]

COMPETITOR_EVENTS = [
    ("Blank Street", "launched a 15% commuter offer within a 3-block radius", "discount"),
    ("Blue Bottle", "extended morning hours to capture the subway surge", "hours"),
    ("Daily Provisions", "increased local digital spend after noticing your repeat rate", "ads"),
    ("Joe & The Juice", "added a fast-pickup shelf for office workers", "operations"),
]


class RetailTwinSimulation:
    def __init__(self):
        self.config = ScenarioConfig()
        self.running = False
        self.speed = 10
        self.day = 1
        self.hour = 7
        self.tick_count = 0
        import random as _random
        self.random = _random.Random(42042)
        self.feed: list[dict[str, Any]] = []
        self.competitor_events: list[dict[str, Any]] = []
        self.agents = self._create_agents()

    def configure(self, config: ScenarioConfig) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self.running = False
        self.day = 1
        self.hour = self.config.opening_time
        self.tick_count = 0
        self.random.seed(42042)
        self.feed = []
        self.competitor_events = []
        self.agents = self._create_agents()

    def start(self, speed: int = 10) -> None:
        self.speed = speed
        self.running = True

    def stop(self) -> None:
        self.running = False

    def set_speed(self, speed: int) -> None:
        self.speed = speed

    def step(self, ticks: int = 1) -> dict[str, Any]:
        import random as _random
        for _ in range(max(1, ticks)):
            self._advance()
        return self.snapshot()

    def _create_agents(self) -> list[dict[str, Any]]:
        import random as _random
        archetypes = [("office", 0.40), ("local", 0.28), ("tourist", 0.17), ("resident", 0.15)]
        agents = []
        for index in range(84):
            roll = self.random.random()
            cumulative = 0
            archetype = "local"
            for name, weight in archetypes:
                cumulative += weight
                if roll <= cumulative:
                    archetype = name
                    break
            agents.append({
                "id": index,
                "type": archetype,
                "x": self.random.uniform(6, 94),
                "y": self.random.uniform(7, 93),
                "target_x": self.random.uniform(8, 92),
                "target_y": self.random.uniform(8, 92),
                "status": "walking",
                "color": {"office": "#a78bfa", "local": "#fbbf24", "tourist": "#fb7185", "resident": "#38bdf8"}[archetype],
            })
        return agents

    def _advance(self) -> None:
        if self.day == 30 and self.hour == 23:
            self.running = False
            return
        self.tick_count += 1
        self.hour += 1
        if self.hour >= 24:
            self.hour = 0
            self.day += 1
        if self.day >= 30 and self.hour >= 23:
            self.day = 30
            self.hour = 23
            self.running = False

        for agent in self.agents:
            dx = agent["target_x"] - agent["x"]
            dy = agent["target_y"] - agent["y"]
            distance = max((dx * dx + dy * dy) ** 0.5, 0.01)
            stride = 1.2 if agent["type"] == "office" else 0.78
            agent["x"] += dx / distance * min(stride, distance)
            agent["y"] += dy / distance * min(stride, distance)
            if distance < 1.5 or self.random.random() < 0.035:
                agent["target_x"] = self.random.uniform(6, 94)
                agent["target_y"] = self.random.uniform(7, 93)
            if self.random.random() < 0.025:
                agent["status"] = self.random.choice(["walking", "browsing", "queued", "checking-in"])

        if self.tick_count % 2 == 0:
            template = self.random.choice(FEED_TEMPLATES)
            self.feed.insert(0, {
                "id": self.tick_count,
                "name": template[0],
                "text": template[1].format(brand=self.config.brand_name, category=self.config.category.lower()),
                "sentiment": template[2],
                "time": f"{max(1, self.tick_count % 58)} min ago",
                "avatar": template[0][0],
            })
            self.feed = self.feed[:5]
        if self.tick_count % 5 == 0:
            event = self.random.choice(COMPETITOR_EVENTS)
            self.competitor_events.insert(0, {
                "id": self.tick_count,
                "competitor": event[0],
                "text": event[1],
                "kind": event[2],
                "time": f"Day {self.day} \u00b7 {self.hour:02d}:00",
            })
            self.competitor_events = self.competitor_events[:4]

    def snapshot(self) -> dict[str, Any]:
        from datetime import datetime, timezone
        elapsed_hours = (self.day - 1) * 24 + self.hour
        day_factor = min(1.0, max(0.55, elapsed_hours / 240))
        enabled = {location.id for location in self.config.locations if location.enabled}
        location_metrics = []
        for location in DISTRICT_LOCATIONS:
            if location.id not in enabled:
                continue
            marketing_lift = 1 + (len(self.config.marketing_channels) * 0.035)
            transactions = round(location.traffic * location.conversion * marketing_lift * day_factor)
            daily_revenue = round(transactions * self.config.average_ticket)
            location_metrics.append({
                "id": location.id,
                "name": location.name,
                "daily_revenue": daily_revenue,
                "annual_revenue": daily_revenue * 365,
                "transactions": transactions,
                "repeat_rate": round(min(0.64, 0.22 + location.conversion * 3.8 + day_factor * 0.08), 2),
                "conversion_rate": round(location.conversion * marketing_lift * 100, 1),
                "foot_traffic": round(location.traffic * (0.98 + day_factor * 0.04)),
                "market_share": round(min(32.0, location.conversion * 240 * marketing_lift), 1),
                "rent": location.rent,
                "payback_months": round(max(12, 25 - location.conversion * 130)),
                "insight": location.context,
            })

        if not location_metrics:
            location_metrics = [{"id": "?", "name": "No location", "daily_revenue": 0, "annual_revenue": 0, "transactions": 0, "repeat_rate": 0, "conversion_rate": 0, "foot_traffic": 0, "market_share": 0, "rent": 0, "payback_months": 0, "insight": ""}]

        best = max(location_metrics, key=lambda item: item["daily_revenue"])
        total_traffic = round(sum(item["foot_traffic"] for item in location_metrics) / max(1, len(location_metrics)))
        total_transactions = best["transactions"]
        is_open = self.config.opening_time <= self.hour < self.config.closing_time
        if not is_open:
            total_transactions = round(total_transactions * 0.18)
            best = {**best, "transactions": total_transactions, "daily_revenue": round(total_transactions * self.config.average_ticket)}
        awareness = min(92, 24 + elapsed_hours * 0.16 + len(self.config.marketing_channels) * 2)
        complete = self.day == 30 and self.hour == 23
        return {
            "running": self.running,
            "complete": complete,
            "day": self.day,
            "hour": self.hour,
            "progress": 100 if complete else round(min(100, elapsed_hours / 720 * 100), 1),
            "active_agents": 10_000,
            "foot_traffic": total_traffic,
            "daily_revenue": best["daily_revenue"],
            "transactions": total_transactions,
            "repeat_customers": round(total_transactions * best["repeat_rate"]),
            "average_ticket": self.config.average_ticket,
            "conversion_rate": best["conversion_rate"],
            "market_share": best["market_share"],
            "cac": round(self.config.marketing_budget / max(1, total_transactions * 7), 2),
            "roi": round((best["annual_revenue"] - self.config.marketing_budget) / max(1, self.config.marketing_budget) * 100, 1),
            "locations": location_metrics,
            "feed": self.feed,
            "competitor_events": self.competitor_events,
            "agents": self.agents,
            "layer_values": {
                "footTraffic": min(100, round(total_traffic / 300)),
                "awareness": round(awareness),
                "sentiment": round(69 + best["repeat_rate"] * 30),
                "revenue": min(100, round(best["market_share"] * 2.8)),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# ---------------------------------------------------------------------------
# AI service
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderConfig:
    name: str
    url: str
    env_vars: tuple[str, ...]
    default_model: str
    kind: str


PROVIDERS: dict[str, ProviderConfig] = {
    "groq": ProviderConfig("groq", "https://api.groq.com/openai/v1/chat/completions", ("GROQ_API_KEY", "EXPO_PUBLIC_GROQ_API_KEY"), "llama-3.3-70b-versatile", "openai"),
    "openrouter": ProviderConfig("openrouter", "https://openrouter.ai/api/v1/chat/completions", ("OPENROUTER_API_KEY", "EXPO_PUBLIC_OPENROUTER_API_KEY"), "meta-llama/llama-3.3-70b-instruct", "openai"),
    "nvidia": ProviderConfig("nvidia", "https://integrate.api.nvidia.com/v1/chat/completions", ("NVIDIA_NIM_API_KEY", "NVIDIA_API_KEY", "EXPO_PUBLIC_NVIDIA_NIM_API_KEY"), "meta/llama-3.3-70b-instruct", "openai"),
    "gemini": ProviderConfig("gemini", "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent", ("GEMINI_API_KEY", "EXPO_PUBLIC_GEMINI_API_KEY"), "gemini-2.5-flash", "gemini"),
    "cohere": ProviderConfig("cohere", "https://api.cohere.com/v2/chat", ("COHERE_API_KEY", "EXPO_PUBLIC_COHERE_API_KEY"), "command-r-plus", "cohere"),
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

    def _api_key(self, config: ProviderConfig) -> Optional[str]:
        for env_var in config.env_vars:
            value = os.getenv(env_var, "").strip()
            if value:
                return value
        return None

    def status(self) -> dict[str, Any]:
        providers = [{"name": name, "configured": bool(self._api_key(config)), "model": config.default_model} for name, config in PROVIDERS.items()]
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
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if config.kind in {"openai", "cohere"}:
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers["x-goog-api-key"] = api_key

        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            if config.kind == "openai":
                request_headers = headers.copy()
                if config.name == "openrouter":
                    request_headers.update({"HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://retail-twin.vercel.app"), "X-Title": "Retail Twin"})
                response = await client.post(config.url, headers=request_headers, json={"model": model, "messages": [{"role": "system", "content": "You are a concise retail location strategy analyst. Return practical executive insight."}, {"role": "user", "content": prompt}], "temperature": 0.35, "max_tokens": 700})
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]

            if config.kind == "gemini":
                response = await client.post(config.url.format(model=model), headers=headers, json={"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.35, "maxOutputTokens": 700}})
                response.raise_for_status()
                return response.json()["candidates"][0]["content"]["parts"][0]["text"]

            response = await client.post(config.url, headers=headers, json={"model": model, "messages": [{"role": "system", "content": "You are a concise retail location strategy analyst. Return practical executive insight."}, {"role": "user", "content": prompt}], "temperature": 0.35, "max_tokens": 700})
            response.raise_for_status()
            content = response.json()["message"]["content"]
            if isinstance(content, list):
                return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
            return str(content)

    def _fallback(self, prompt: str) -> str:
        if "Location B" in prompt or "Broadway Subway" in prompt:
            return "Location B wins because the subway exit creates a natural pause point: fewer raw passersby, stronger conversion, and more repeat visits. Protect the morning commute window, staff for the lunch surge, and use the first campaign to build a habit with nearby office workers."
        return "The strongest opportunity is the location with the clearest customer routine, not necessarily the most impressions. Prioritize repeat behavior, conversion context, and operating-hour demand before committing capital."


# ---------------------------------------------------------------------------
# App singleton (persists across warm serverless invocations)
# ---------------------------------------------------------------------------

simulation = RetailTwinSimulation()
ai_service = AIService()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    simulation.stop()


app = FastAPI(title="Retail Twin API", version="0.2.0", lifespan=lifespan)

frontend_origin = os.getenv("FRONTEND_ORIGIN", "").strip()
allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
if frontend_origin:
    allowed_origins.append(frontend_origin.rstrip("/"))
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "retail-twin", "simulation": simulation.running}


@app.get("/api/ai/status")
async def ai_status():
    return ai_service.status()


@app.post("/api/ai/generate", response_model=AIResponse)
async def ai_generate(request: AIRequest):
    result = await ai_service.generate(request.prompt, request.provider, request.model)
    return result.__dict__


@app.get("/api/scenario")
async def get_scenario():
    return simulation.config.model_dump()


@app.post("/api/scenario")
async def configure_scenario(config: ScenarioConfig):
    simulation.configure(config)
    return simulation.snapshot()


@app.get("/api/snapshot")
async def get_snapshot():
    if simulation.running:
        simulation.step(1)
    return simulation.snapshot()


@app.post("/api/simulation/start")
async def start_simulation(command: SimulationCommand = SimulationCommand()):
    simulation.start(command.speed)
    return simulation.snapshot()


@app.post("/api/simulation/stop")
async def stop_simulation():
    simulation.stop()
    return simulation.snapshot()


@app.post("/api/simulation/reset")
async def reset_simulation():
    simulation.reset()
    return simulation.snapshot()


@app.post("/api/simulation/speed")
async def change_speed(command: SimulationCommand):
    simulation.set_speed(command.speed)
    return simulation.snapshot()
