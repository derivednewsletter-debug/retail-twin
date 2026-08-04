"""
Historical analytics storage and aggregation.

Stores simulation snapshots over time and provides aggregated views
for weather patterns, day-of-week effects, and trend analysis.

Note: Uses in-memory storage (persists across warm serverless invocations).
For production, replace with a database like Upstash Redis or Turso.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class SnapshotRecord:
    """A single recorded snapshot from the simulation."""
    day: int
    hour: int
    timestamp: float
    daily_revenue: float
    transactions: int
    foot_traffic: int
    conversion_rate: float
    repeat_rate: float
    market_share: float
    weather_condition: str
    weather_traffic_modifier: float
    transit_status: str
    transit_traffic_modifier: float
    real_world_modifier: float
    category: str
    brand_name: str


@dataclass
class DailyAggregate:
    """Aggregated data for a single simulated day."""
    day: int
    avg_revenue: float
    total_revenue: float
    avg_transactions: float
    avg_foot_traffic: float
    avg_conversion_rate: float
    avg_repeat_rate: float
    avg_weather_modifier: float
    avg_transit_modifier: float
    dominant_weather: str
    dominant_transit_status: str
    revenue_range: tuple[float, float]  # min, max
    data_points: int


@dataclass
class WeatherPattern:
    """Aggregated data by weather condition."""
    condition: str
    avg_revenue: float
    avg_traffic: float
    avg_conversion: float
    sample_count: int
    revenue_impact_pct: float  # % change vs overall average


@dataclass
class DayOfWeekPattern:
    """Aggregated data by day of week."""
    day_name: str
    day_index: int  # 0=Monday
    avg_revenue: float
    avg_traffic: float
    avg_conversion: float
    sample_count: int
    revenue_impact_pct: float


@dataclass
class HourlyPattern:
    """Aggregated data by hour of day."""
    hour: int
    avg_revenue: float
    avg_traffic: float
    sample_count: int


@dataclass
class AnalyticsSummary:
    """Complete analytics summary."""
    total_snapshots: int
    simulation_days_covered: int
    date_range: str  # "Day 1 - Day 30"
    overall_avg_revenue: float
    overall_total_revenue: float
    peak_revenue_day: int
    peak_revenue_hour: int
    daily_trend: list[DailyAggregate]
    weather_patterns: list[WeatherPattern]
    day_of_week_patterns: list[DayOfWeekPattern]
    hourly_patterns: list[HourlyPattern]
    weather_impact_summary: str
    dow_impact_summary: str
    key_insight: str


class AnalyticsStore:
    """In-memory analytics store for simulation snapshots."""

    def __init__(self) -> None:
        self._records: list[SnapshotRecord] = []
        self._max_records = 2000  # Limit memory usage

    def record_snapshot(self, snapshot: dict[str, Any], config: dict[str, Any]) -> None:
        """Record a simulation snapshot for historical analysis."""
        weather = snapshot.get("weather", {})
        transit = snapshot.get("transit", {})

        record = SnapshotRecord(
            day=snapshot.get("day", 1),
            hour=snapshot.get("hour", 7),
            timestamp=time.time(),
            daily_revenue=snapshot.get("daily_revenue", 0),
            transactions=snapshot.get("transactions", 0),
            foot_traffic=snapshot.get("foot_traffic", 0),
            conversion_rate=snapshot.get("conversion_rate", 0),
            repeat_rate=snapshot.get("repeat_customers", 0) / max(1, snapshot.get("transactions", 1)),
            market_share=snapshot.get("market_share", 0),
            weather_condition=weather.get("condition", "clear"),
            weather_traffic_modifier=weather.get("traffic_modifier", 1.0),
            transit_status=transit.get("status", "good"),
            transit_traffic_modifier=transit.get("traffic_modifier", 1.0),
            real_world_modifier=snapshot.get("real_world_modifier", 1.0),
            category=config.get("category", "Premium coffee"),
            brand_name=config.get("brand_name", "Northstar Coffee"),
        )

        self._records.append(record)

        # Trim old records if over limit
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]

    def get_summary(self) -> AnalyticsSummary:
        """Generate a complete analytics summary from stored records."""
        if not self._records:
            return self._empty_summary()

        records = self._records

        # Overall stats
        revenues = [r.daily_revenue for r in records]
        overall_avg = sum(revenues) / len(revenues)
        overall_total = sum(revenues)

        # Find peak
        peak_record = max(records, key=lambda r: r.daily_revenue)

        # Daily aggregates
        daily = self._aggregate_by_day(records)

        # Weather patterns
        weather = self._aggregate_by_weather(records, overall_avg)

        # Day of week patterns
        dow = self._aggregate_by_dow(records, overall_avg)

        # Hourly patterns
        hourly = self._aggregate_by_hour(records)

        # Generate insights
        weather_insight = self._generate_weather_insight(weather)
        dow_insight = self._generate_dow_insight(dow)
        key_insight = self._generate_key_insight(daily, weather, dow)

        return AnalyticsSummary(
            total_snapshots=len(records),
            simulation_days_covered=len(set(r.day for r in records)),
            date_range=f"Day {min(r.day for r in records)} – Day {max(r.day for r in records)}",
            overall_avg_revenue=round(overall_avg, 2),
            overall_total_revenue=round(overall_total, 2),
            peak_revenue_day=peak_record.day,
            peak_revenue_hour=peak_record.hour,
            daily_trend=daily,
            weather_patterns=weather,
            day_of_week_patterns=dow,
            hourly_patterns=hourly,
            weather_impact_summary=weather_insight,
            dow_impact_summary=dow_insight,
            key_insight=key_insight,
        )

    def _aggregate_by_day(self, records: list[SnapshotRecord]) -> list[DailyAggregate]:
        """Group records by day and compute aggregates."""
        by_day: dict[int, list[SnapshotRecord]] = {}
        for r in records:
            by_day.setdefault(r.day, []).append(r)

        result = []
        for day in sorted(by_day.keys()):
            day_records = by_day[day]
            revenues = [r.daily_revenue for r in day_records]
            result.append(DailyAggregate(
                day=day,
                avg_revenue=round(sum(revenues) / len(revenues), 2),
                total_revenue=round(sum(revenues), 2),
                avg_transactions=round(sum(r.transactions for r in day_records) / len(day_records), 1),
                avg_foot_traffic=round(sum(r.foot_traffic for r in day_records) / len(day_records), 1),
                avg_conversion_rate=round(sum(r.conversion_rate for r in day_records) / len(day_records), 2),
                avg_repeat_rate=round(sum(r.repeat_rate for r in day_records) / len(day_records), 4),
                avg_weather_modifier=round(sum(r.weather_traffic_modifier for r in day_records) / len(day_records), 3),
                avg_transit_modifier=round(sum(r.transit_traffic_modifier for r in day_records) / len(day_records), 3),
                dominant_weather=max(set(r.weather_condition for r in day_records), key=lambda c: sum(1 for r in day_records if r.weather_condition == c)),
                dominant_transit_status=max(set(r.transit_status for r in day_records), key=lambda s: sum(1 for r in day_records if r.transit_status == s)),
                revenue_range=(min(revenues), max(revenues)),
                data_points=len(day_records),
            ))
        return result

    def _aggregate_by_weather(self, records: list[SnapshotRecord], overall_avg: float) -> list[WeatherPattern]:
        """Group records by weather condition."""
        by_weather: dict[str, list[SnapshotRecord]] = {}
        for r in records:
            by_weather.setdefault(r.weather_condition, []).append(r)

        result = []
        for condition in sorted(by_weather.keys()):
            recs = by_weather[condition]
            avg_rev = sum(r.daily_revenue for r in recs) / len(recs)
            impact = ((avg_rev - overall_avg) / max(0.01, overall_avg)) * 100
            result.append(WeatherPattern(
                condition=condition,
                avg_revenue=round(avg_rev, 2),
                avg_traffic=round(sum(r.foot_traffic for r in recs) / len(recs), 1),
                avg_conversion=round(sum(r.conversion_rate for r in recs) / len(recs), 2),
                sample_count=len(recs),
                revenue_impact_pct=round(impact, 1),
            ))
        return sorted(result, key=lambda w: w.avg_revenue, reverse=True)

    def _aggregate_by_dow(self, records: list[SnapshotRecord], overall_avg: float) -> list[DayOfWeekPattern]:
        """Group records by day of week (Day 1 = Monday)."""
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        by_dow: dict[int, list[SnapshotRecord]] = {}
        for r in records:
            dow = (r.day - 1) % 7
            by_dow.setdefault(dow, []).append(r)

        result = []
        for dow_idx in range(7):
            recs = by_dow.get(dow_idx, [])
            if not recs:
                continue
            avg_rev = sum(r.daily_revenue for r in recs) / len(recs)
            impact = ((avg_rev - overall_avg) / max(0.01, overall_avg)) * 100
            result.append(DayOfWeekPattern(
                day_name=day_names[dow_idx],
                day_index=dow_idx,
                avg_revenue=round(avg_rev, 2),
                avg_traffic=round(sum(r.foot_traffic for r in recs) / len(recs), 1),
                avg_conversion=round(sum(r.conversion_rate for r in recs) / len(recs), 2),
                sample_count=len(recs),
                revenue_impact_pct=round(impact, 1),
            ))
        return result

    def _aggregate_by_hour(self, records: list[SnapshotRecord]) -> list[HourlyPattern]:
        """Group records by hour of day."""
        by_hour: dict[int, list[SnapshotRecord]] = {}
        for r in records:
            by_hour.setdefault(r.hour, []).append(r)

        result = []
        for hour in sorted(by_hour.keys()):
            recs = by_hour[hour]
            result.append(HourlyPattern(
                hour=hour,
                avg_revenue=round(sum(r.daily_revenue for r in recs) / len(recs), 2),
                avg_traffic=round(sum(r.foot_traffic for r in recs) / len(recs), 1),
                sample_count=len(recs),
            ))
        return result

    def _generate_weather_insight(self, patterns: list[WeatherPattern]) -> str:
        if not patterns:
            return "No weather data recorded yet."
        best = patterns[0]
        worst = patterns[-1]
        return f"{best.condition.title()} days generate ${best.avg_revenue:,.0f} avg revenue (+{best.revenue_impact_pct:+.1f}%), while {worst.condition} days drop to ${worst.avg_revenue:,.0f} ({worst.revenue_impact_pct:+.1f}%)."

    def _generate_dow_insight(self, patterns: list[DayOfWeekPattern]) -> str:
        if not patterns:
            return "No day-of-week data recorded yet."
        best = max(patterns, key=lambda p: p.avg_revenue)
        worst = min(patterns, key=lambda p: p.avg_revenue)
        return f"{best.day_name}s peak at ${best.avg_revenue:,.0f} avg revenue (+{best.revenue_impact_pct:+.1f}%), while {worst.day_name}s are slowest at ${worst.avg_revenue:,.0f} ({worst.revenue_impact_pct:+.1f}%)."

    def _generate_key_insight(
        self,
        daily: list[DailyAggregate],
        weather: list[WeatherPattern],
        dow: list[DayOfWeekPattern],
    ) -> str:
        if not daily:
            return "Run a simulation to generate insights."

        # Find the biggest revenue driver
        insights = []

        if weather and len(weather) >= 2:
            spread = weather[0].revenue_impact_pct - weather[-1].revenue_impact_pct
            if spread > 5:
                insights.append(f"Weather is the #1 revenue driver — a {spread:.0f} percentage point swing between {weather[0].condition} and {weather[-1].condition} days")

        if dow and len(dow) >= 2:
            best_dow = max(dow, key=lambda d: d.avg_revenue)
            worst_dow = min(dow, key=lambda d: d.avg_revenue)
            dow_spread = best_dow.revenue_impact_pct - worst_dow.revenue_impact_pct
            if dow_spread > 3:
                insights.append(f"{best_dow.day_name}s outperform {worst_dow.day_name}s by {dow_spread:.0f} points")

        if daily:
            trend = daily[-1].avg_revenue - daily[0].avg_revenue
            if abs(trend) > 100:
                direction = "growing" if trend > 0 else "declining"
                insights.append(f"Revenue is {direction} over the simulation period (${abs(trend):,.0f} change)")

        if not insights:
            insights.append("The simulation shows consistent performance across weather and day-of-week patterns")

        return ". ".join(insights) + "."

    def _empty_summary(self) -> AnalyticsSummary:
        return AnalyticsSummary(
            total_snapshots=0,
            simulation_days_covered=0,
            date_range="No data",
            overall_avg_revenue=0,
            overall_total_revenue=0,
            peak_revenue_day=0,
            peak_revenue_hour=0,
            daily_trend=[],
            weather_patterns=[],
            day_of_week_patterns=[],
            hourly_patterns=[],
            weather_impact_summary="No data recorded yet. Run a simulation to see weather impact analysis.",
            dow_impact_summary="No data recorded yet. Run a simulation to see day-of-week patterns.",
            key_insight="Run a simulation to generate historical analytics insights.",
        )


# Global singleton
analytics_store = AnalyticsStore()
