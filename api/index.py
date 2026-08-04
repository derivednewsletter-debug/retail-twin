"""
Retail Twin API — Vercel-compatible entry point.

This module creates a FastAPI app with a catch-all route that handles
all /api/* paths. Vercel's Python runtime serves this at /api/index,
and we use rewrites to route /api/* here.
"""
from __future__ import annotations

import asyncio
import os
import random as _random
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# Import from sibling modules
import sys
import os

# Ensure sibling modules are importable
_api_dir = os.path.dirname(os.path.abspath(__file__))
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

try:
    from data_services import (
        build_simulation_context, SimulationContext,
        HOURLY_PATTERN, CATEGORY_HOUR_CURVES,
    )
    from ai_content import AIContentGenerator
    from analytics import analytics_store
except ImportError as e:
    # Fallback: provide minimal stubs if imports fail
    import traceback
    traceback.print_exc()
    raise

load_dotenv()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

Category = Literal[
    "Premium coffee", "Healthy fast casual", "Athletic apparel",
    "Fitness studio", "Beauty retail", "Specialty grocery",
]

MarketingChannel = Literal[
    "Grand opening", "Transit ads", "Local influencers",
    "Opening discount", "Social media",
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
    locations: list[LocationConfig] = Field(
        default_factory=lambda: [LocationConfig(id="A"), LocationConfig(id="B"), LocationConfig(id="C")],
        min_length=1,
    )
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
        if not any(loc.enabled for loc in value):
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
# District data
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

FALLBACK_FEED = [
    ("Maya R.", "Walked past the new {brand} on my way to the studio — the line is already moving fast.", "positive"),
    ("Jordan L.", "The subway exit is the perfect spot for a quick {category} stop.", "positive"),
    ("Priya S.", "A little pricier than Blank Street, but the experience feels much more intentional.", "neutral"),
    ("Eli T.", "Honestly did not expect to become a regular this quickly. The staff remembers my order.", "positive"),
    ("Noah K.", "Lunch rush is intense today. Wonder if they will add more seating.", "neutral"),
    ("Sofia M.", "The matcha latte here is leagues better than the chain down the block.", "positive"),
    ("Marcus D.", "Stopped in after a gallery visit — the space feels curated but welcoming.", "positive"),
    ("Aisha T.", "Price point is steep for a daily habit, but perfect for a weekend treat.", "neutral"),
    ("Chris P.", "Found it on a side street. Feels like a local secret already.", "positive"),
    ("Diana W.", "Brought my team here for a working lunch. Everyone loved it.", "positive"),
    ("Ryan K.", "The line was out the door at noon. Had to come back at 3pm.", "neutral"),
    ("Zara L.", "First time trying their cold brew. Worth the walk from Spring St.", "positive"),
    ("Kevin H.", "Not bad, but Blue Bottle is right there and I have a routine.", "negative"),
    ("Olivia R.", "The pastry case sold out by 10am. Need to come earlier.", "neutral"),
    ("James F.", "Great WiFi, good vibes. New go-to spot for remote work.", "positive"),
]

FALLBACK_COMPETITORS = [
    ("Blank Street", "launched a 15% commuter offer within a 3-block radius", "discount"),
    ("Blue Bottle", "extended morning hours to capture the subway surge", "hours"),
    ("Daily Provisions", "increased local digital spend after noticing your repeat rate", "ads"),
    ("Joe & The Juice", "added a fast-pickup shelf for office workers", "operations"),
    ("Starbucks", "deployed a mobile order pickup station at the corner", "operations"),
    ("La Colombe", "launched a BOGO latte promo targeting SoHo commuters", "discount"),
    ("Sweetgreen", "increased delivery radius to cover your trade area", "operations"),
    ("Tory Burch", "hosted a weekend pop-up drawing foot traffic to the block", "ads"),
]


# ---------------------------------------------------------------------------
# Simulation engine
# ---------------------------------------------------------------------------

class RetailTwinSimulation:
    def __init__(self) -> None:
        self.config = ScenarioConfig()
        self.running = False
        self.speed = 10
        self.day = 1
        self.hour = 7
        self.tick_count = 0
        self.rng = _random.Random(42042)
        self.feed: list[dict[str, Any]] = []
        self.competitor_events: list[dict[str, Any]] = []
        self.agents = self._create_agents()
        self.context: Optional[SimulationContext] = None
        self.ai_generator = AIContentGenerator()
        self._last_ai_tick = 0
        self.weather_summary = "clear"
        self.demographic_summary = "dense urban, high walkability"

    def configure(self, config: ScenarioConfig) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self.running = False
        self.day = 1
        self.hour = self.config.opening_time
        self.tick_count = 0
        self.rng.seed(42042)
        self.feed = []
        self.competitor_events = []
        self.agents = self._create_agents()
        self.context = None
        self.weather_summary = "clear"
        self.demographic_summary = "dense urban, high walkability"
        self._last_ai_tick = 0

    def start(self, speed: int = 10) -> None:
        self.speed = speed
        self.running = True

    def stop(self) -> None:
        self.running = False

    def set_speed(self, speed: int) -> None:
        self.speed = speed

    def _create_agents(self) -> list[dict[str, Any]]:
        archetypes = [("office", 0.40), ("local", 0.28), ("tourist", 0.17), ("resident", 0.15)]
        agents = []
        for index in range(84):
            roll = self.rng.random()
            cumulative = 0.0
            archetype = "local"
            for name, weight in archetypes:
                cumulative += weight
                if roll <= cumulative:
                    archetype = name
                    break
            agents.append({
                "id": index, "type": archetype,
                "x": self.rng.uniform(6, 94), "y": self.rng.uniform(7, 93),
                "target_x": self.rng.uniform(8, 92), "target_y": self.rng.uniform(8, 92),
                "status": "walking",
                "color": {"office": "#a78bfa", "local": "#fbbf24", "tourist": "#fb7185", "resident": "#38bdf8"}[archetype],
            })
        return agents

    async def _advance_async(self) -> None:
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
            return
        if self.tick_count % 6 == 0 or self.context is None:
            try:
                self.context = await build_simulation_context(self.config.category, self.hour, self.day)
                self.weather_summary = self.context.weather.condition
            except Exception:
                self.context = None
        self._move_agents()
        traffic_mult = self.context.overall_traffic_multiplier if self.context else 1.0
        if self.tick_count % 2 == 0 and self.rng.random() < (0.12 * traffic_mult) + 0.15:
            post = await self._generate_feed_post()
            if post:
                self.feed.insert(0, {
                    "id": self.tick_count, "name": post.get("name", "Anonymous"),
                    "text": post.get("text", "Visited the new store."),
                    "sentiment": post.get("sentiment", "neutral"),
                    "time": f"{max(1, self.tick_count % 58)} min ago",
                    "avatar": post.get("name", "A")[0] if post.get("name") else "A",
                })
                self.feed = self.feed[:8]
        if self.tick_count % 8 == 0:
            event = await self._generate_competitor_event()
            if event:
                self.competitor_events.insert(0, {
                    "id": self.tick_count, "competitor": event.get("competitor", "Blank Street"),
                    "text": event.get("text", "adjusted local pricing"),
                    "kind": event.get("kind", "discount"),
                    "time": f"Day {self.day} · {self.hour:02d}:00",
                })
                self.competitor_events = self.competitor_events[:6]

    def _move_agents(self) -> None:
        for agent in self.agents:
            dx = agent["target_x"] - agent["x"]
            dy = agent["target_y"] - agent["y"]
            distance = max((dx * dx + dy * dy) ** 0.5, 0.01)
            stride = 1.2 if agent["type"] == "office" else 0.78
            agent["x"] += dx / distance * min(stride, distance)
            agent["y"] += dy / distance * min(stride, distance)
            if distance < 1.5 or self.rng.random() < 0.035:
                agent["target_x"] = self.rng.uniform(6, 94)
                agent["target_y"] = self.rng.uniform(7, 93)
            if self.rng.random() < 0.025:
                agent["status"] = self.rng.choice(["walking", "browsing", "queued", "checking-in"])

    async def _generate_feed_post(self) -> Optional[dict[str, Any]]:
        try:
            posts = await self.ai_generator.generate_consumer_posts(
                brand=self.config.brand_name, category=self.config.category,
                weather_condition=self.weather_summary, hour=self.hour,
                location_name=self.rng.choice([loc.name for loc in DISTRICT_LOCATIONS]),
            )
            if posts:
                return self.rng.choice(posts)
        except Exception:
            pass
        template = self.rng.choice(FALLBACK_FEED)
        return {"name": template[0], "text": template[1].format(brand=self.config.brand_name, category=self.config.category.lower()), "sentiment": template[2]}

    async def _generate_competitor_event(self) -> Optional[dict[str, Any]]:
        try:
            event = await self.ai_generator.generate_competitor_event(
                brand=self.config.brand_name,
                competitors=["Blank Street", "Blue Bottle", "Daily Provisions", "Joe & The Juice", "Starbucks", "La Colombe"],
                hour=self.hour, weather_condition=self.weather_summary,
            )
            if event:
                return event
        except Exception:
            pass
        event = self.rng.choice(FALLBACK_COMPETITORS)
        return {"competitor": event[0], "text": event[1], "kind": event[2]}

    def snapshot(self) -> dict[str, Any]:
        elapsed_hours = (self.day - 1) * 24 + self.hour
        day_factor = min(1.0, max(0.55, elapsed_hours / 240))
        enabled = {loc.id for loc in self.config.locations if loc.enabled}
        hourly_mod = HOURLY_PATTERN.get(self.hour, 1.0)
        day_mod = [0.90, 0.95, 1.0, 1.05, 1.15, 1.20, 1.10][(self.day - 1) % 7]
        cat_curve = CATEGORY_HOUR_CURVES.get(self.config.category, {})
        cat_mod = cat_curve.get(self.hour, 0.5)
        weather_mod = self.context.weather.traffic_modifier if self.context else 1.0
        subway_mod = self.context.subway_traffic_modifier if self.context else 1.0
        real_world_mult = round(hourly_mod * day_mod * cat_mod * weather_mod, 3)
        location_metrics = []
        for location in DISTRICT_LOCATIONS:
            if location.id not in enabled:
                continue
            marketing_lift = 1 + (len(self.config.marketing_channels) * 0.035)
            # Location B (Broadway Subway) gets additional subway traffic modifier
            loc_mult = real_world_mult * subway_mod if location.id == "B" else real_world_mult
            base_traffic = location.traffic * loc_mult
            transactions = round(base_traffic * location.conversion * marketing_lift * day_factor)
            daily_revenue = round(transactions * self.config.average_ticket)
            location_metrics.append({
                "id": location.id, "name": location.name,
                "daily_revenue": daily_revenue, "annual_revenue": daily_revenue * 365,
                "transactions": transactions,
                "repeat_rate": round(min(0.64, 0.22 + location.conversion * 3.8 + day_factor * 0.08), 2),
                "conversion_rate": round(location.conversion * marketing_lift * 100, 1),
                "foot_traffic": round(base_traffic),
                "market_share": round(min(32.0, location.conversion * 240 * marketing_lift), 1),
                "rent": location.rent,
                "payback_months": round(max(12, 25 - location.conversion * 130)),
                "insight": location.context,
            })
        if not location_metrics:
            location_metrics = [{"id": "?", "name": "No location", "daily_revenue": 0, "annual_revenue": 0, "transactions": 0, "repeat_rate": 0, "conversion_rate": 0, "foot_traffic": 0, "market_share": 0, "rent": 0, "payback_months": 0, "insight": ""}]
        best = max(location_metrics, key=lambda x: x["daily_revenue"])
        total_traffic = round(sum(x["foot_traffic"] for x in location_metrics) / max(1, len(location_metrics)))
        total_transactions = best["transactions"]
        is_open = self.config.opening_time <= self.hour < self.config.closing_time
        if not is_open:
            total_transactions = round(total_transactions * 0.18)
            best = {**best, "transactions": total_transactions, "daily_revenue": round(total_transactions * self.config.average_ticket)}
        awareness = min(92, 24 + elapsed_hours * 0.16 + len(self.config.marketing_channels) * 2)
        complete = self.day == 30 and self.hour == 23
        weather_info = {}
        transit_info = {}
        if self.context:
            weather_info = {"temperature_f": self.context.weather.temperature_f, "condition": self.context.weather.condition, "wind_mph": self.context.weather.wind_mph, "traffic_modifier": self.context.weather.traffic_modifier}
            transit_info = {
                "status": self.context.transit.overall_status,
                "traffic_modifier": self.context.transit.traffic_modifier,
                "lines_affected": self.context.transit.lines_affected,
                "alerts": [{"line": a.line, "status": a.status, "header": a.header, "severity": a.severity} for a in self.context.transit.alerts[:5]],
                "last_updated": self.context.transit.last_updated,
            }
        return {
            "running": self.running, "complete": complete, "day": self.day, "hour": self.hour,
            "progress": 100 if complete else round(min(100, elapsed_hours / 720 * 100), 1),
            "active_agents": 10_000, "foot_traffic": total_traffic,
            "daily_revenue": best["daily_revenue"], "transactions": total_transactions,
            "repeat_customers": round(total_transactions * best["repeat_rate"]),
            "average_ticket": self.config.average_ticket,
            "conversion_rate": best["conversion_rate"], "market_share": best["market_share"],
            "cac": round(self.config.marketing_budget / max(1, total_transactions * 7), 2),
            "roi": round((best["annual_revenue"] - self.config.marketing_budget) / max(1, self.config.marketing_budget) * 100, 1),
            "locations": location_metrics, "feed": self.feed, "competitor_events": self.competitor_events,
            "agents": self.agents,
            "layer_values": {"footTraffic": min(100, round(total_traffic / 300)), "awareness": round(awareness), "sentiment": round(69 + best["repeat_rate"] * 30), "revenue": min(100, round(best["market_share"] * 2.8))},
            "weather": weather_info, "transit": transit_info, "real_world_modifier": real_world_mult,
            "data_sources": {"weather": "Open-Meteo" if self.context else "fallback", "demographics": "US Census" if self.context else "fallback", "nyc_open_data": "NYC 311" if self.context and self.context.nyc_events else "fallback", "transit": "MTA GTFS" if self.context and self.context.transit.alerts else "fallback", "consumer_feed": "AI-generated" if self.ai_generator.available_providers() else "deterministic"},
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
    def __init__(self, timeout_seconds: float = 12.0) -> None:
        self.timeout = httpx.Timeout(timeout_seconds, connect=5.0)

    def _api_key(self, config: ProviderConfig) -> Optional[str]:
        for env_var in config.env_vars:
            value = os.getenv(env_var, "").strip()
            if value:
                return value
        return None

    def status(self) -> dict[str, Any]:
        providers = [{"name": name, "configured": bool(self._api_key(config)), "model": config.default_model} for name, config in PROVIDERS.items()]
        data_sources = [{"name": "Open-Meteo Weather", "configured": True, "type": "data"}, {"name": "US Census Demographics", "configured": True, "type": "data"}, {"name": "NYC Open Data", "configured": True, "type": "data"}]
        return {"providers": providers, "data_sources": data_sources, "fallback": "deterministic simulation copy", "mode": "ai-enabled" if any(p["configured"] for p in providers) else "deterministic"}

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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if config.kind == "openai":
                request_headers = headers.copy()
                if config.name == "openrouter":
                    request_headers.update({"HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://retail-twin.vercel.app"), "X-Title": "Retail Twin"})
                response = await client.post(config.url, headers=request_headers, json={"model": model, "messages": [{"role": "system", "content": "You are a concise retail location strategy analyst."}, {"role": "user", "content": prompt}], "temperature": 0.35, "max_tokens": 700})
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
            if config.kind == "gemini":
                response = await client.post(config.url.format(model=model), headers=headers, json={"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.35, "maxOutputTokens": 700}})
                response.raise_for_status()
                return response.json()["candidates"][0]["content"]["parts"][0]["text"]
            response = await client.post(config.url, headers=headers, json={"model": model, "message": prompt, "temperature": 0.35, "max_tokens": 700})
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
            if isinstance(content, list):
                return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
            return str(content)

    def _fallback(self, prompt: str) -> str:
        if "Location B" in prompt or "Broadway Subway" in prompt:
            return "Location B wins because the subway exit creates a natural pause point: fewer raw passersby, stronger conversion, and more repeat visits."
        return "The strongest opportunity is the location with the clearest customer routine, not necessarily the most impressions."


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

simulation = RetailTwinSimulation()
ai_service = AIService()


# ---------------------------------------------------------------------------
# FastAPI app with catch-all routing for Vercel
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    simulation.stop()


app = FastAPI(title="Retail Twin API", version="0.3.0", lifespan=lifespan)

# Wrap for Vercel Lambda runtime
try:
    from mangum import Mangum
    handler = Mangum(app)
except ImportError:
    handler = None

frontend_origin = os.getenv("FRONTEND_ORIGIN", "").strip()
allowed_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
if frontend_origin:
    allowed_origins.append(frontend_origin.rstrip("/"))
if not frontend_origin:
    allowed_origins.append("*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Route handlers — named endpoints (not catch-all)
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "retail-twin", "version": "0.3.0", "simulation": simulation.running, "providers": ai_service.status()["providers"]}

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
        await simulation._advance_async()
        # Record snapshot for analytics
        snap = simulation.snapshot()
        analytics_store.record_snapshot(snap, simulation.config.model_dump())
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

@app.get("/api/data/weather")
async def get_weather():
    from data_services import get_weather as fetch_weather
    w = await fetch_weather()
    return {"temperature_f": w.temperature_f, "condition": w.condition, "wind_mph": w.wind_mph, "precipitation_mm": w.precipitation_mm, "traffic_modifier": w.traffic_modifier}

@app.get("/api/data/demographics")
async def get_demographics():
    from data_services import get_demographics as fetch_demo
    d = await fetch_demo()
    return {"population": d.population, "median_income": d.median_income, "median_age": d.median_age, "college_pct": d.college_pct, "walk_pct": d.walk_pct, "density_label": d.density_label}

@app.get("/api/data/nyc-events")
async def get_nyc_events():
    from data_services import get_nyc_events as fetch_events
    events = await fetch_events()
    return [{"type": e.type, "description": e.description, "neighborhood": e.neighborhood, "severity": e.severity} for e in events]

@app.get("/api/analytics")
async def get_analytics():
    summary = analytics_store.get_summary()
    return {
        "total_snapshots": summary.total_snapshots,
        "simulation_days_covered": summary.simulation_days_covered,
        "date_range": summary.date_range,
        "overall_avg_revenue": summary.overall_avg_revenue,
        "overall_total_revenue": summary.overall_total_revenue,
        "peak_revenue_day": summary.peak_revenue_day,
        "peak_revenue_hour": summary.peak_revenue_hour,
        "weather_impact_summary": summary.weather_impact_summary,
        "dow_impact_summary": summary.dow_impact_summary,
        "key_insight": summary.key_insight,
        "daily_trend": [{"day": d.day, "avg_revenue": d.avg_revenue, "total_revenue": d.total_revenue, "avg_traffic": d.avg_foot_traffic, "weather": d.dominant_weather, "weather_mod": d.avg_weather_modifier, "transit_mod": d.avg_transit_modifier} for d in summary.daily_trend],
        "weather_patterns": [{"condition": w.condition, "avg_revenue": w.avg_revenue, "avg_traffic": w.avg_traffic, "impact_pct": w.revenue_impact_pct, "samples": w.sample_count} for w in summary.weather_patterns],
        "day_of_week": [{"day": d.day_name, "index": d.day_index, "avg_revenue": d.avg_revenue, "avg_traffic": d.avg_traffic, "impact_pct": d.revenue_impact_pct, "samples": d.sample_count} for d in summary.day_of_week_patterns],
        "hourly": [{"hour": h.hour, "avg_revenue": h.avg_revenue, "avg_traffic": h.avg_traffic, "samples": h.sample_count} for h in summary.hourly_patterns],
    }

@app.post("/api/analytics/reset")
async def reset_analytics():
    analytics_store._records.clear()
    return {"status": "ok", "message": "Analytics data cleared"}

@app.get("/api/data/transit")
async def get_transit():
    from data_services import get_transit_status as fetch_transit
    t = await fetch_transit()
    return {
        "status": t.overall_status,
        "traffic_modifier": t.traffic_modifier,
        "lines_affected": t.lines_affected,
        "alerts": [{"line": a.line, "status": a.status, "header": a.header, "description": a.description, "severity": a.severity} for a in t.alerts],
        "last_updated": t.last_updated,
    }


# ---------------------------------------------------------------------------
# Catch-all handler — catches any /api/* route not matched above
# This is needed because Vercel's rewrite sends all /api/* to this file,
# but only the paths defined as actual FastAPI routes will be served.
# ---------------------------------------------------------------------------

@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def catch_all(path: str, request: Request):
    """Catch-all for unmatched /api/* routes."""
    # If we reach here, the path wasn't matched by any specific route
    return JSONResponse(
        status_code=404,
        content={"error": f"Route /api/{path} not found", "available_routes": [
            "/api/health", "/api/scenario", "/api/snapshot",
            "/api/simulation/start", "/api/simulation/stop", "/api/simulation/reset", "/api/simulation/speed",
            "/api/ai/status", "/api/ai/generate",
            "/api/data/weather", "/api/data/demographics", "/api/data/nyc-events",
        ]},
    )
