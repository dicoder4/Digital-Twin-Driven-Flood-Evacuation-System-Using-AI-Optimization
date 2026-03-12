"""
weather_client.py
─────────────────
Fetches real-time and historical weather data using the Open-Meteo API
(free, no API key required).  Acts as the bridge between the GenAI agent
and live weather data without needing mcp_weather_server to be running.

It can also act as a thin client IF you start isdaniel/mcp_weather_server
as a sidecar subprocess — see WeatherClient.from_mcp_server().

Data returned always includes:
  - precipitation_mm          : accumulated rain in last 24 h (mm)
  - precipitation_probability : probability of rain (%) from hourly forecast
  - temp_c                    : current temperature (°C)
  - wind_speed_kmh            : wind speed (km/h)
  - description               : human-readable condition string

Open-Meteo endpoints used:
  Forecast  → https://api.open-meteo.com/v1/forecast
  Historical→ https://archive-api.open-meteo.com/v1/archive
"""

from __future__ import annotations

import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

# ── Open-Meteo base URLs ──────────────────────────────────────────────────────
_FORECAST_BASE  = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_BASE   = "https://archive-api.open-meteo.com/v1/archive"
_GEOCODE_BASE   = "https://geocoding-api.open-meteo.com/v1/search"

_TIMEOUT_S = 10   # HTTP timeout in seconds


def _get(url: str, params: dict) -> dict:
    """Synchronous HTTP GET returning parsed JSON."""
    qs  = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{qs}", headers={"User-Agent": "UrbanFloodTwin/1.0"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
        return json.loads(resp.read().decode())


def _geocode(city_label: str) -> tuple[float, float]:
    """
    Resolve a free-form city label to (lat, lon) using Open-Meteo Geocoding.
    Falls back to Bengaluru city centre if not found.
    """
    data = _get(_GEOCODE_BASE, {"name": city_label, "count": 1, "language": "en", "format": "json"})
    results = data.get("results", [])
    if results:
        r = results[0]
        return float(r["latitude"]), float(r["longitude"])
    # Default: Bengaluru city centre
    return 12.9716, 77.5946


# ── WMO weather code → human description ────────────────────────────────────
_WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherClient:
    """
    High-level weather client for the flood GenAI pipeline.

    Parameters
    ----------
    lat : float         Latitude of the hobli centroid
    lon : float         Longitude of the hobli centroid
    city_label : str    Human-readable label ("Sarjapura-1, Bengaluru Urban, India")
    """

    def __init__(self, lat: float, lon: float, city_label: str = "Bengaluru, India"):
        self.lat        = lat
        self.lon        = lon
        self.city_label = city_label

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_current(self) -> dict:
        """
        Fetch current conditions + today's precipitation forecast.

        Returns
        -------
        dict with keys:
            precipitation_mm, precipitation_probability, temp_c,
            wind_speed_kmh, description, source, fetched_at
        """
        params = {
            "latitude":   self.lat,
            "longitude":  self.lon,
            "current":    "temperature_2m,wind_speed_10m,weather_code,precipitation",
            "hourly":     "precipitation_probability,precipitation",
            "forecast_days": 1,
            "timezone":   "Asia/Kolkata",
        }
        try:
            data = _get(_FORECAST_BASE, params)
        except Exception as exc:
            return self._error_payload(f"Open-Meteo forecast failed: {exc}")

        current = data.get("current", {})
        hourly  = data.get("hourly", {})

        temp_c        = current.get("temperature_2m", None)
        wind_kmh      = current.get("wind_speed_10m", None)
        wmo_code      = int(current.get("weather_code", 0))
        precip_now_mm = float(current.get("precipitation", 0.0))

        # Sum ALL hourly precipitation values for today
        hourly_precip    = hourly.get("precipitation", [])
        hourly_prob      = hourly.get("precipitation_probability", [])
        total_precip_mm  = round(sum(float(v) for v in hourly_precip if v is not None), 2)
        max_prob         = max((int(v) for v in hourly_prob if v is not None), default=0)

        description = _WMO_CODES.get(wmo_code, f"Weather code {wmo_code}")

        return {
            "precipitation_mm":          total_precip_mm,
            "precipitation_probability": max_prob,
            "temp_c":                    temp_c,
            "wind_speed_kmh":            wind_kmh,
            "description":               description,
            "source":                    "open-meteo-forecast",
            "fetched_at":                datetime.now(timezone.utc).isoformat(),
        }

    def get_historical(self, days_back: int = 1) -> dict:
        """
        Fetch accumulated precipitation for the past *days_back* days from
        the Open-Meteo historical archive.

        Parameters
        ----------
        days_back : int   How many days to go back (1 = yesterday, 7 = last week)

        Returns
        -------
        dict with same keys as get_current()
        """
        today     = datetime.now(timezone.utc).date()
        end_date  = today - timedelta(days=1)
        start_date = end_date - timedelta(days=max(0, days_back - 1))

        params = {
            "latitude":   self.lat,
            "longitude":  self.lon,
            "start_date": start_date.isoformat(),
            "end_date":   end_date.isoformat(),
            "daily":      "precipitation_sum,temperature_2m_max,wind_speed_10m_max",
            "timezone":   "Asia/Kolkata",
        }
        try:
            data = _get(_ARCHIVE_BASE, params)
        except Exception as exc:
            return self._error_payload(f"Open-Meteo archive failed: {exc}")

        daily = data.get("daily", {})
        precip_vals = [float(v) for v in daily.get("precipitation_sum", []) if v is not None]
        temp_vals   = [float(v) for v in daily.get("temperature_2m_max", []) if v is not None]
        wind_vals   = [float(v) for v in daily.get("wind_speed_10m_max",  []) if v is not None]

        total_precip_mm = round(sum(precip_vals), 2)
        temp_c          = round(max(temp_vals), 1) if temp_vals else None
        wind_kmh        = round(max(wind_vals), 1) if wind_vals else None

        return {
            "precipitation_mm":          total_precip_mm,
            "precipitation_probability": 100 if total_precip_mm > 0 else 0,
            "temp_c":                    temp_c,
            "wind_speed_kmh":            wind_kmh,
            "description":               f"Historical: {days_back}-day accumulated rainfall",
            "source":                    "open-meteo-archive",
            "fetched_at":                datetime.now(timezone.utc).isoformat(),
            "period":                    f"{start_date.isoformat()} to {end_date.isoformat()}",
        }

    # ── Factory: hobli centroid coords (shortcut) ──────────────────────────────

    @classmethod
    def from_hobli_info(cls, hobli_info: dict) -> "WeatherClient":
        """
        Convenience constructor — pass the dict returned by param_resolver.resolve_hobli().
        """
        return cls(
            lat        = hobli_info["lat"],
            lon        = hobli_info["lon"],
            city_label = hobli_info.get("city_label", "Bengaluru, India"),
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _error_payload(msg: str) -> dict:
        return {
            "precipitation_mm":          None,
            "precipitation_probability": None,
            "temp_c":                    None,
            "wind_speed_kmh":            None,
            "description":               msg,
            "source":                    "error",
            "fetched_at":                datetime.now(timezone.utc).isoformat(),
        }
