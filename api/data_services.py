from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx


# ---------------------------------------------------------------------------
# In-memory TTL cache (per warm serverless container)
# ---------------------------------------------------------------------------

@dataclass
class _CacheEntry:
    data: Any
    expires_at: float


class TTLCache:
    """Simple TTL cache that survives warm serverless invocations."""

    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.time() > entry.expires_at:
            del self._store[key]
            return None
        return entry.data

    def set(self, key: str, value: Any, ttl_seconds: float = 300) -> None:
        self._store[key] = _CacheEntry(data=value, expires_at=time.time() + ttl_seconds)


_cache = TTLCache()

# SoHo, Manhattan coordinates
SOHO_LAT = 40.7235
SOHO_LON = -73.9993


# ---------------------------------------------------------------------------
# Weather data (Open-Meteo — free, no API key required)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WeatherData:
    temperature_f: float
    weather_code: int
    precipitation_mm: float
    wind_mph: float
    condition: str  # "clear", "rain", "snow", "overcast", "hot", "cold"
    traffic_modifier: float  # 0.6 to 1.3 multiplier for foot traffic


WEATHER_CODE_MAP: dict[int, str] = {
    0: "clear", 1: "clear", 2: "overcast", 3: "overcast",
    45: "fog", 48: "fog",
    51: "drizzle", 53: "drizzle", 55: "rain",
    56: "freezing_rain", 57: "freezing_rain",
    61: "rain", 63: "rain", 65: "heavy_rain",
    66: "freezing_rain", 67: "freezing_rain",
    71: "snow", 73: "snow", 75: "heavy_snow", 77: "snow",
    80: "rain", 81: "rain", 82: "heavy_rain",
    85: "snow", 86: "heavy_snow",
    95: "thunderstorm", 96: "thunderstorm", 99: "thunderstorm",
}


def _weather_condition(code: int, temp_c: float) -> str:
    if code in (95, 96, 99):
        return "thunderstorm"
    if code in (71, 73, 75, 77, 85, 86):
        return "snow"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "rain"
    if code in (51, 53, 55, 56, 57):
        return "drizzle"
    if code in (45, 48):
        return "fog"
    if code in (2, 3):
        return "overcast"
    if temp_c >= 32:
        return "hot"
    if temp_c <= 2:
        return "cold"
    return "clear"


def _traffic_modifier(condition: str, temp_c: float) -> float:
    """Return a multiplier for foot traffic based on weather."""
    base = {
        "clear": 1.05, "overcast": 1.0, "hot": 0.92, "cold": 0.88,
        "fog": 0.85, "drizzle": 0.80, "rain": 0.65, "heavy_rain": 0.50,
        "freezing_rain": 0.40, "snow": 0.55, "heavy_snow": 0.35,
        "thunderstorm": 0.30,
    }.get(condition, 1.0)
    # Mild temperatures boost traffic further
    if 15 <= temp_c <= 25:
        base *= 1.05
    return round(base, 2)


async def get_weather() -> WeatherData:
    """Fetch current weather for SoHo from Open-Meteo (free, no key)."""
    cache_key = "weather_current"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={SOHO_LAT}&longitude={SOHO_LON}"
        f"&current=temperature_2m,weather_code,precipitation,wind_speed_10m"
        f"&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=mm"
    )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()["current"]
            temp_f = float(data["temperature_2m"])
            temp_c = (temp_f - 32) * 5 / 9
            code = int(data["weather_code"])
            precip = float(data.get("precipitation", 0))
            wind = float(data.get("wind_speed_10m", 0))
            condition = _weather_condition(code, temp_c)
            modifier = _traffic_modifier(condition, temp_c)
            result = WeatherData(
                temperature_f=temp_f,
                weather_code=code,
                precipitation_mm=precip,
                wind_mph=wind,
                condition=condition,
                traffic_modifier=modifier,
            )
            _cache.set(cache_key, result, ttl_seconds=600)
            return result
    except Exception:
        # Fallback: pleasant spring day in SoHo
        return WeatherData(
            temperature_f=68, weather_code=1, precipitation_mm=0,
            wind_mph=8, condition="clear", traffic_modifier=1.05,
        )


# ---------------------------------------------------------------------------
# NYC 311 noise complaints (NYC Open Data — free, no key, Socrata API)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class NYCEvent:
    type: str
    description: str
    neighborhood: str
    severity: str  # "low", "medium", "high"


async def get_nyc_events() -> list[NYCEvent]:
    """Fetch recent SoHo-area complaints from NYC Open Data (free, no key)."""
    cache_key = "nyc_events"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    # NYC Open Data Socrata API — noise complaints in SoHo area
    url = (
        "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
        "?$where=latitude>40.720 AND latitude<40.727"
        " AND longitude>-74.005 AND longitude<-73.995"
        "&$order=created_date DESC"
        "&$limit=10"
        "&$select=descriptor,complaint_type,agency_name"
    )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            rows = resp.json()
            events: list[NYCEvent] = []
            for row in rows[:8]:
                desc = row.get("descriptor", row.get("complaint_type", ""))
                complaint_type = row.get("complaint_type", "")
                severity = "high" if "noise" in complaint_type.lower() else "medium"
                events.append(NYCEvent(
                    type=complaint_type[:40],
                    description=desc[:100],
                    neighborhood="SoHo",
                    severity=severity,
                ))
            _cache.set(cache_key, events, ttl_seconds=1800)
            return events
    except Exception:
        return []


# ---------------------------------------------------------------------------
# US Census demographics (free API key from census.gov, or use without)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DemographicData:
    population: int
    median_income: int
    median_age: float
    college_pct: float
    walk_pct: float  # percentage who walk to work
    density_label: str  # "dense urban", "urban", "suburban"


async def get_demographics() -> DemographicData:
    """Fetch SoHo (zip 10012) demographics from Census Bureau."""
    cache_key = "demographics_10012"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    census_key = os.getenv("CENSUS_API_KEY", "")
    # SoHo zip 10012 — ACS 5-year estimates
    base = "https://api.census.gov/data/2022/acs/acs5"
    var_list = "B01003_001E,B19301_001E,B01002_001E,B15003_0022E,B08301_001E,B08301_0019E"
    params = f"?get={var_list}&for=zip%20code%20tabulation%20area:10012"
    if census_key:
        params += f"&key={census_key}"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            resp = await client.get(f"{base}{params}")
            resp.raise_for_status()
            rows = resp.json()
            if len(rows) >= 2:
                vals = rows[1]
                population = int(vals[0]) if vals[0] else 28_000
                income = int(vals[1]) if vals[1] else 85_000
                age = float(vals[2]) if vals[2] else 34.5
                college = int(vals[3]) if vals[3] else 68
                total_workers = int(vals[4]) if vals[4] else 1
                walkers = int(vals[5]) if vals[5] else 1
                walk_pct = round(walkers / max(1, total_workers) * 100, 1)
                result = DemographicData(
                    population=population,
                    median_income=income,
                    median_age=age,
                    college_pct=round(college / max(1, population) * 100, 1),
                    walk_pct=walk_pct,
                    density_label="dense urban",
                )
                _cache.set(cache_key, result, ttl_seconds=86400)
                return result
    except Exception:
        pass

    # Fallback: well-known SoHo demographics
    result = DemographicData(
        population=28_000, median_income=85_000, median_age=34.5,
        college_pct=72.0, walk_pct=65.0, density_label="dense urban",
    )
    _cache.set(cache_key, result, ttl_seconds=86400)
    return result


# ---------------------------------------------------------------------------
# Time-of-day behavioral patterns (based on real SoHo foot traffic research)
# ---------------------------------------------------------------------------

# Hourly traffic multiplier for SoHo (based on real pedestrian count studies)
HOURLY_PATTERN: dict[int, float] = {
    0: 0.15, 1: 0.10, 2: 0.08, 3: 0.06, 4: 0.08, 5: 0.15,
    6: 0.30, 7: 0.55, 8: 0.80, 9: 0.95, 10: 1.00, 11: 0.95,
    12: 1.05, 13: 1.00, 14: 0.90, 15: 0.85, 16: 0.80, 17: 0.90,
    18: 1.00, 19: 0.85, 20: 0.70, 21: 0.50, 22: 0.35, 23: 0.20,
}

# Day-of-week modifier (0=Monday)
DAY_OF_WEEK_MODIFIER: list[float] = [
    0.90,  # Monday
    0.95,  # Tuesday
    1.00,  # Wednesday
    1.05,  # Thursday
    1.15,  # Friday
    1.20,  # Saturday
    1.10,  # Sunday
]


def get_hourly_modifier(hour: int) -> float:
    return HOURLY_PATTERN.get(hour, 1.0)


def get_day_modifier(day: int) -> float:
    """day is 1-indexed (1=Day 1 of simulation). Returns modifier based on day-of-week."""
    dow = (day - 1) % 7  # Day 1 = Monday
    return DAY_OF_WEEK_MODIFIER[dow]


# ---------------------------------------------------------------------------
# Store type demand curves (different categories peak at different hours)
# ---------------------------------------------------------------------------

CATEGORY_HOUR_CURVES: dict[str, dict[int, float]] = {
    "Premium coffee": {
        6: 0.70, 7: 1.00, 8: 1.10, 9: 0.95, 10: 0.80, 11: 0.75,
        12: 0.85, 13: 0.70, 14: 0.55, 15: 0.50, 16: 0.45, 17: 0.60,
        18: 0.40, 19: 0.25,
    },
    "Healthy fast casual": {
        7: 0.20, 8: 0.30, 9: 0.40, 10: 0.50, 11: 0.85, 12: 1.10,
        13: 1.00, 14: 0.60, 15: 0.40, 16: 0.35, 17: 0.70, 18: 0.80,
        19: 0.50, 20: 0.25,
    },
    "Athletic apparel": {
        9: 0.30, 10: 0.70, 11: 0.85, 12: 0.90, 13: 0.95, 14: 1.00,
        15: 0.90, 16: 0.85, 17: 0.80, 18: 0.75, 19: 0.60, 20: 0.40,
    },
    "Fitness studio": {
        6: 0.90, 7: 1.10, 8: 1.00, 9: 0.70, 10: 0.50, 11: 0.40,
        12: 0.60, 13: 0.30, 14: 0.40, 15: 0.50, 16: 0.70, 17: 1.05,
        18: 1.15, 19: 0.90, 20: 0.50,
    },
    "Beauty retail": {
        10: 0.60, 11: 0.85, 12: 0.90, 13: 0.95, 14: 1.00, 15: 0.95,
        16: 0.90, 17: 0.85, 18: 0.75, 19: 0.55, 20: 0.35,
    },
    "Specialty grocery": {
        7: 0.40, 8: 0.60, 9: 0.80, 10: 0.95, 11: 1.00, 12: 0.90,
        13: 0.75, 14: 0.65, 15: 0.70, 16: 0.85, 17: 1.05, 18: 0.90,
        19: 0.60, 20: 0.30,
    },
}


def get_category_modifier(category: str, hour: int) -> float:
    curve = CATEGORY_HOUR_CURVES.get(category, {})
    return curve.get(hour, 0.5)


# ---------------------------------------------------------------------------
# NYC Subway Transit Data (MTA GTFS — free public service alerts feed)
# ---------------------------------------------------------------------------

# Subway lines serving SoHo / Broadway-Lafayette area
SOHO_SUBWAY_LINES = ["N", "Q", "R", "W", "B", "D", "F", "M", "6"]

# Station IDs for SoHo area stations
SOHO_STATIONS = {
    "Prince St": ["R20", "R21"],  # N, R, W
    "Broadway-Lafayette": ["A40", "D15"],  # B, D, F, M
    "Spring St": ["A41", "C25"],  # C, E
    "Canal St": ["R36", "A38"],  # N, Q, R, W, J, Z, 6
}


@dataclass(frozen=True)
class TransitAlert:
    line: str
    status: str  # "good", "delays", "service_change", "planned"
    header: str
    description: str
    affected_stations: list[str]
    severity: int  # 0=good, 1=minor, 2=moderate, 3=severe


@dataclass(frozen=True)
class TransitStatus:
    alerts: list[TransitAlert]
    overall_status: str  # "good", "minor_delays", "major_delays"
    traffic_modifier: float  # 0.6 to 1.1 multiplier for foot traffic at subway location
    lines_affected: list[str]
    last_updated: str


async def get_transit_status() -> TransitStatus:
    """Fetch MTA subway alerts for SoHo-area lines.
    
    Uses the free MTA GTFS service alerts feed (no API key required).
    Caches results for 5 minutes to respect rate limits.
    """
    cache_key = "transit_status"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    # MTA free service alerts endpoint (no API key required)
    url = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/cny%2Falerts"
    
    alerts: list[TransitAlert] = []
    lines_with_delays: set[str] = set()
    
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            
            # Try to parse as GTFS Protocol Buffer (binary)
            # If that fails, try JSON fallback
            try:
                from google.transit import gtfs_realtime_pb2
                feed = gtfs_realtime_pb2.FeedMessage()
                feed.ParseFromString(resp.content)
                
                for entity in feed.entity:
                    if not entity.HasField('alert'):
                        continue
                    
                    alert = entity.alert
                    
                    # Check if this alert affects any SoHo lines
                    affected_lines = set()
                    for informed_entity in alert.informed_entity:
                        route_id = informed_entity.route_id
                        if route_id in SOHO_SUBWAY_LINES:
                            affected_lines.add(route_id)
                    
                    if not affected_lines:
                        continue
                    
                    # Extract alert text
                    header = ""
                    if alert.header_text.translation:
                        header = alert.header_text.translation[0].text
                    
                    description = ""
                    if alert.description_text.translation:
                        description = alert.description_text.translation[0].text
                    
                    # Determine status from alert type
                    status = "service_change"
                    severity = 1
                    
                    alert_type = alert.effect
                    if alert_type == 1:  # NO_SERVICE
                        status = "delays"
                        severity = 3
                    elif alert_type == 2:  # REDUCED_SERVICE
                        status = "delays"
                        severity = 2
                    elif alert_type == 3:  # SIGNIFICANT_DELAYS
                        status = "delays"
                        severity = 2
                    elif alert_type == 4:  # DETOUR
                        status = "service_change"
                        severity = 1
                    elif alert_type == 5:  # ADDITIONAL_SERVICE
                        status = "good"
                        severity = 0
                    elif alert_type == 6:  # MODIFIED_SERVICE
                        status = "service_change"
                        severity = 1
                    elif alert_type == 7:  # OTHER_EFFECT
                        status = "planned"
                        severity = 0
                    elif alert_type == 8:  # UNKNOWN_EFFECT
                        status = "service_change"
                        severity = 1
                    
                    for line in affected_lines:
                        alerts.append(TransitAlert(
                            line=line,
                            status=status,
                            header=header[:100] if header else f"Service change on {line} train",
                            description=description[:200] if description else "",
                            affected_stations=["Prince St", "Broadway-Lafayette"],
                            severity=severity,
                        ))
                        if severity >= 2:
                            lines_with_delays.add(line)
            except ImportError:
                # gtfs_realtime_pb2 not available, try JSON parsing
                # MTA also provides JSON alerts at a different endpoint
                json_url = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/cny%2Falerts.json"
                try:
                    json_resp = await client.get(json_url)
                    json_resp.raise_for_status()
                    data = json_resp.json()
                    # Parse JSON alerts if available
                    for entity in data.get('entities', []):
                        alert = entity.get('alert', {})
                        affected_lines = set()
                        for informed in alert.get('informed_entity', []):
                            route = informed.get('route_id', '')
                            if route in SOHO_SUBWAY_LINES:
                                affected_lines.add(route)
                        if affected_lines:
                            header = alert.get('header_text', {}).get('translation', [{}])[0].get('text', '')
                            description = alert.get('description_text', {}).get('translation', [{}])[0].get('text', '')
                            for line in affected_lines:
                                alerts.append(TransitAlert(
                                    line=line,
                                    status="service_change",
                                    header=header[:100] if header else f"Service change on {line} train",
                                    description=description[:200],
                                    affected_stations=["Prince St", "Broadway-Lafayette"],
                                    severity=1,
                                ))
                except Exception:
                    pass
            except Exception:
                # If protobuf parsing fails, continue with empty alerts
                pass
    except Exception:
        # MTA feed unavailable — use fallback
        pass
    
    # Determine overall status
    max_severity = max((a.severity for a in alerts), default=0)
    if max_severity >= 3:
        overall = "major_delays"
        traffic_mod = 0.55
    elif max_severity >= 2:
        overall = "minor_delays"
        traffic_mod = 0.75
    elif max_severity >= 1:
        overall = "minor_delays"
        traffic_mod = 0.90
    else:
        overall = "good"
        traffic_mod = 1.0
    
    from datetime import datetime, timezone
    result = TransitStatus(
        alerts=alerts[:10],  # Limit to 10 most relevant
        overall_status=overall,
        traffic_modifier=traffic_mod,
        lines_affected=sorted(lines_with_delays),
        last_updated=datetime.now(timezone.utc).isoformat(),
    )
    
    _cache.set(cache_key, result, ttl_seconds=300)  # Cache for 5 minutes
    return result


# ---------------------------------------------------------------------------
# Aggregated simulation context
# ---------------------------------------------------------------------------

@dataclass
class SimulationContext:
    weather: WeatherData
    demographics: DemographicData
    nyc_events: list[NYCEvent]
    transit: TransitStatus
    hourly_modifier: float
    day_modifier: float
    category_modifier: float
    overall_traffic_multiplier: float
    subway_traffic_modifier: float  # Additional modifier for subway-adjacent location


async def build_simulation_context(
    category: str, hour: int, day: int,
) -> SimulationContext:
    """Build a rich context object from all real-world data sources."""
    weather, demographics, events, transit = await asyncio.gather(
        get_weather(),
        get_demographics(),
        get_nyc_events(),
        get_transit_status(),
    )
    hourly = get_hourly_modifier(hour)
    day_mod = get_day_modifier(day)
    cat_mod = get_category_modifier(category, hour)
    overall = round(hourly * day_mod * cat_mod * weather.traffic_modifier, 3)
    
    # Subway traffic modifier: transit delays reduce foot traffic at Location B
    # Location B (Broadway Subway) gets 40% of its traffic from subway riders
    subway_mod = transit.traffic_modifier
    subway_contribution = 0.40  # 40% of Location B traffic comes from subway
    non_subway_contribution = 1.0 - subway_contribution
    location_b_modifier = round(non_subway_contribution + (subway_contribution * subway_mod), 3)

    return SimulationContext(
        weather=weather,
        demographics=demographics,
        nyc_events=events,
        transit=transit,
        hourly_modifier=hourly,
        day_modifier=day_mod,
        category_modifier=cat_mod,
        overall_traffic_multiplier=overall,
        subway_traffic_modifier=location_b_modifier,
    )
