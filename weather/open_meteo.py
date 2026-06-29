"""
weather/open_meteo.py — Open-Meteo API client (gratis, tanpa API key)
=====================================================================
Sumber cuaca utama untuk AgriTwin, menggantikan OWM.
API: https://open-meteo.com/en/docs

Fitur:
  - Current weather (temperature, humidity, wind, rain, solar radiation)
  - Forecast 16 hari (hourly + daily)
  - Historis 7 hari
  - In-memory cache (TTL 10 menit), Upstash Redis jika tersedia
"""
import datetime
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests

# ── Cache layer — Upstash Redis jika ada, fallback in-memory dict ────────────
_CACHE: Dict[str, Tuple[float, Any]] = {}   # key → (expire_ts, data)
_CACHE_TTL = 600  # 10 menit default

_redis = None
try:
    _upstash_url   = os.environ.get("UPSTASH_REDIS_REST_URL", "")
    _upstash_token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
    if _upstash_url and _upstash_token:
        from upstash_redis import Redis as _UpstashRedis   # type: ignore
        _redis = _UpstashRedis(url=_upstash_url, token=_upstash_token)
except ImportError:
    pass


def _cache_get(key: str) -> Optional[Any]:
    """Read from Redis if available, else in-memory."""
    if _redis:
        try:
            import json
            raw = _redis.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            pass
    entry = _CACHE.get(key)
    if entry and entry[0] > time.time():
        return entry[1]
    return None


def _cache_set(key: str, value: Any, ttl: int = _CACHE_TTL):
    """Write to Redis if available, else in-memory."""
    if _redis:
        try:
            import json
            _redis.set(key, json.dumps(value), ex=ttl)
        except Exception:
            pass
    _CACHE[key] = (time.time() + ttl, value)


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class OpenMeteoWeather:
    """Current weather dari Open-Meteo."""
    temperature_c:       float = 0.0
    humidity_pct:        float = 0.0
    wind_speed_ms:       float = 0.0
    precipitation_mm:    float = 0.0
    cloud_cover_pct:     float = 0.0
    solar_radiation_wm2: float = 0.0
    pressure_hpa:        float = 1013.0
    dew_point_c:         float = 0.0
    wind_direction_deg:  float = 0.0
    is_day:              bool  = True
    source:              str   = "open-meteo"
    timestamp:           str   = ""


@dataclass
class OpenMeteoForecast:
    """Forecast point (hourly atau daily)."""
    time:             str   = ""
    temperature_c:    float = 0.0
    humidity_pct:     float = 0.0
    precipitation_mm: float = 0.0
    wind_speed_ms:    float = 0.0
    solar_radiation_wm2: float = 0.0
    cloud_cover_pct:  float = 0.0


# ── API Functions ────────────────────────────────────────────────────────────

_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_USER_AGENT = "AgriTwin/1.0"


def fetch_current(lat: float, lon: float) -> Optional[OpenMeteoWeather]:
    """Ambil cuaca saat ini untuk koordinat tertentu.

    Returns OpenMeteoWeather atau None jika gagal.
    Cache key: "wx:{lat:.3f}:{lon:.3f}:current"
    """
    cache_key = f"wx:{lat:.3f}:{lon:.3f}:current"
    cached = _cache_get(cache_key)
    if cached:
        return OpenMeteoWeather(**cached)

    try:
        r = requests.get(_BASE_URL, params={
            "latitude":  round(lat, 4),
            "longitude": round(lon, 4),
            "current": ",".join([
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "wind_speed_10m",
                "wind_direction_10m",
                "cloud_cover",
                "surface_pressure",
                "shortwave_radiation",
                "is_day",
            ]),
            "timezone": "auto",
        }, headers={"User-Agent": _USER_AGENT}, timeout=8)
        r.raise_for_status()
        data = r.json()
        cur = data.get("current", {})

        temp = _safe_float(cur.get("temperature_2m"))
        hum  = _safe_float(cur.get("relative_humidity_2m"))

        result = OpenMeteoWeather(
            temperature_c       = temp,
            humidity_pct        = hum,
            wind_speed_ms       = _safe_float(cur.get("wind_speed_10m")),
            precipitation_mm    = _safe_float(cur.get("precipitation")),
            cloud_cover_pct     = _safe_float(cur.get("cloud_cover")),
            solar_radiation_wm2 = _safe_float(cur.get("shortwave_radiation")),
            pressure_hpa        = _safe_float(cur.get("surface_pressure"), 1013.0),
            dew_point_c         = _dew_point(temp, hum),
            wind_direction_deg  = _safe_float(cur.get("wind_direction_10m")),
            is_day              = bool(cur.get("is_day", 1)),
            source              = "open-meteo",
            timestamp           = cur.get("time", datetime.datetime.now().isoformat()),
        )

        # Cache result
        from dataclasses import asdict
        _cache_set(cache_key, asdict(result), ttl=600)
        return result

    except Exception:
        return None


def fetch_forecast(lat: float, lon: float,
                   days: int = 16) -> List[OpenMeteoForecast]:
    """Forecast hourly untuk N hari ke depan (max 16).

    Cache key: "wx:{lat:.3f}:{lon:.3f}:fc:{days}"
    Returns list of OpenMeteoForecast (hourly resolution).
    """
    days = min(days, 16)
    cache_key = f"wx:{lat:.3f}:{lon:.3f}:fc:{days}"
    cached = _cache_get(cache_key)
    if cached:
        return [OpenMeteoForecast(**c) for c in cached]

    try:
        r = requests.get(_BASE_URL, params={
            "latitude":  round(lat, 4),
            "longitude": round(lon, 4),
            "hourly": ",".join([
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "wind_speed_10m",
                "shortwave_radiation",
                "cloud_cover",
            ]),
            "forecast_days": days,
            "timezone": "auto",
        }, headers={"User-Agent": _USER_AGENT}, timeout=12)
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly", {})

        times = hourly.get("time", [])
        result = []
        for i, t in enumerate(times):
            result.append(OpenMeteoForecast(
                time             = t,
                temperature_c    = _safe_float_idx(hourly.get("temperature_2m"), i),
                humidity_pct     = _safe_float_idx(hourly.get("relative_humidity_2m"), i),
                precipitation_mm = _safe_float_idx(hourly.get("precipitation"), i),
                wind_speed_ms    = _safe_float_idx(hourly.get("wind_speed_10m"), i),
                solar_radiation_wm2 = _safe_float_idx(hourly.get("shortwave_radiation"), i),
                cloud_cover_pct  = _safe_float_idx(hourly.get("cloud_cover"), i),
            ))

        from dataclasses import asdict
        _cache_set(cache_key, [asdict(f) for f in result], ttl=1800)  # 30 min cache
        return result

    except Exception:
        return []


def fetch_history(lat: float, lon: float,
                  days_back: int = 7) -> List[OpenMeteoForecast]:
    """Historis cuaca N hari ke belakang.

    Menggunakan Open-Meteo Archive API.
    Cache key: "wx:{lat:.3f}:{lon:.3f}:hist:{date}"
    """
    end_date   = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=days_back)
    cache_key  = f"wx:{lat:.3f}:{lon:.3f}:hist:{start_date.isoformat()}"
    cached = _cache_get(cache_key)
    if cached:
        return [OpenMeteoForecast(**c) for c in cached]

    try:
        # Archive API (free, ERA5 reanalysis untuk data historis)
        r = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
            "latitude":   round(lat, 4),
            "longitude":  round(lon, 4),
            "start_date": start_date.isoformat(),
            "end_date":   end_date.isoformat(),
            "hourly": ",".join([
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "wind_speed_10m",
                "shortwave_radiation",
                "cloud_cover",
            ]),
            "timezone": "auto",
        }, headers={"User-Agent": _USER_AGENT}, timeout=12)
        r.raise_for_status()
        data = r.json()
        hourly = data.get("hourly", {})

        times = hourly.get("time", [])
        result = []
        for i, t in enumerate(times):
            result.append(OpenMeteoForecast(
                time             = t,
                temperature_c    = _safe_float_idx(hourly.get("temperature_2m"), i),
                humidity_pct     = _safe_float_idx(hourly.get("relative_humidity_2m"), i),
                precipitation_mm = _safe_float_idx(hourly.get("precipitation"), i),
                wind_speed_ms    = _safe_float_idx(hourly.get("wind_speed_10m"), i),
                solar_radiation_wm2 = _safe_float_idx(hourly.get("shortwave_radiation"), i),
                cloud_cover_pct  = _safe_float_idx(hourly.get("cloud_cover"), i),
            ))

        from dataclasses import asdict
        _cache_set(cache_key, [asdict(f) for f in result], ttl=3600)  # 1 hour
        return result

    except Exception:
        return []


# ── Utility ──────────────────────────────────────────────────────────────────

def _safe_float(val: Any, fallback: float = 0.0) -> float:
    try:
        v = float(val)
        return v if math.isfinite(v) else fallback
    except (TypeError, ValueError):
        return fallback


def _safe_float_idx(arr: Optional[list], idx: int, fallback: float = 0.0) -> float:
    if arr is None or idx >= len(arr):
        return fallback
    return _safe_float(arr[idx], fallback)


def _dew_point(temp_c: float, rh_pct: float) -> float:
    """August-Roche-Magnus dew point approximation."""
    a, b = 17.625, 243.04
    try:
        rh = max(0.01, min(100.0, rh_pct))
        alpha = (a * temp_c) / (b + temp_c) + math.log(rh / 100.0)
        return round(b * alpha / (a - alpha), 1)
    except (ValueError, ZeroDivisionError):
        return temp_c - 5.0
