from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .models import ScenarioConfig


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
        self.random = random.Random(42042)
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
        for _ in range(max(1, ticks)):
            self._advance()
        return self.snapshot()

    def _create_agents(self) -> list[dict[str, Any]]:
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
                "time": f"Day {self.day} · {self.hour:02d}:00",
            })
            self.competitor_events = self.competitor_events[:4]

    def snapshot(self) -> dict[str, Any]:
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
