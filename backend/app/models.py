from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


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


class LocationMetrics(BaseModel):
    id: str
    name: str
    daily_revenue: int
    annual_revenue: int
    transactions: int
    repeat_rate: float
    conversion_rate: float
    foot_traffic: int
    market_share: float
    rent: int
    payback_months: int
    insight: str


class SimulationSnapshot(BaseModel):
    running: bool
    day: int
    hour: int
    progress: float
    active_agents: int
    foot_traffic: int
    daily_revenue: int
    transactions: int
    repeat_customers: int
    average_ticket: float
    conversion_rate: float
    market_share: float
    cac: float
    roi: float
    locations: list[LocationMetrics]
    feed: list[dict]
    competitor_events: list[dict]
    agents: list[dict]
    layer_values: dict[str, float]
