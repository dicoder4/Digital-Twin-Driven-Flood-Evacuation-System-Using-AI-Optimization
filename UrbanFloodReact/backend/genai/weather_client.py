import os
import requests
from datetime import datetime, timezone


class WeatherClient:
    def __init__(self, lat: float, lon: float, display_name: str = "Unknown"):
        self.lat = lat
        self.lon = lon
        self.display_name = display_name

    @classmethod
    def from_hobli_info(cls, hobli_info: dict):
        return cls(
            lat=hobli_info["lat"],
            lon=hobli_info["lon"],
            display_name=hobli_info["display"]
        )

    def get_current(self) -> dict:
        """
        Fetch current weather. Source priority:

        1. WeatherAPI.com  — real station observations, actual precip_mm.
                            Requires WEATHERAPI_KEY in .env (free: 1M calls/month).
                            Sign up at: https://www.weatherapi.com/

        2. MET Norway + wttr.in (combined, both free, no key needed)
                            MET Norway provides the best free precipitation value
                            (verified against live data: returned 0.3mm during a
                            Bengaluru thunderstorm where wttr.in showed 0.0mm).
                            wttr.in provides the accurate condition description
                            (confirmed correct code 389 = "Light thunderstorm").

        3. wttr.in alone   — fallback with precipitation floor estimate if MET Norway
                            is unreachable.

        4. Open-Meteo      — absolute last resort. NWP forecast model, NOT live
                            observations. During a Bengaluru thunderstorm it returned
                            weather_code=1 ("Mainly Clear"). Highly unreliable for
                            convective events in tropical India.
        """
        # --- Primary: WeatherAPI.com (real observed precip, needs key) ---
        api_key = os.getenv("WEATHERAPI_KEY") or os.getenv("WEATHER_API_KEY")
        if api_key:
            result = self._fetch_weatherapi(api_key)
            if result and result.get("source") != "error":
                return result

        # --- Secondary: MET Norway precip + wttr.in condition (best free combo) ---
        result = self._fetch_combined_met_wttr()
        if result and result.get("source") != "error":
            return result

        # --- Tertiary: wttr.in alone with precip floor estimate ---
        result = self._fetch_wttr_in()
        if result and result.get("source") != "error":
            return result

        # --- Last resort: Open-Meteo (forecast model, unreliable for India) ---
        return self._fetch_open_meteo()

    # ── WeatherAPI.com ────────────────────────────────────────────────────────

    def _fetch_weatherapi(self, api_key: str) -> dict:
        """
        WeatherAPI.com — real station-observed precip_mm.
        Free tier: 1,000,000 calls/month.
        https://www.weatherapi.com/docs/#apis-realtime
        """
        try:
            url = (
                f"http://api.weatherapi.com/v1/current.json"
                f"?key={api_key}&q={self.lat},{self.lon}&aqi=no"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            current = data.get("current", {})
            condition = current.get("condition", {})
            return {
                "source": "weatherapi.com",
                "temp_c": float(current.get("temp_c", 0.0)),
                "precipitation_mm": float(current.get("precip_mm", 0.0)),
                "humidity": int(current.get("humidity", 0)),
                "cloud_cover": int(current.get("cloud", 0)),
                "weather_code": int(condition.get("code", 0)),
                "description": condition.get("text", "Unknown").strip(),
            }
        except Exception as e:
            return {"source": "error", "description": f"WeatherAPI failed: {str(e)}"}

    # ── MET Norway + wttr.in (combined) ──────────────────────────────────────

    # MET Norway symbol_code → human readable description
    # Full list: https://api.met.no/weatherapi/weathericon/2.0/
    _MET_SYMBOL_MAP = {
        "clearsky":                  "Clear",
        "fair":                      "Mainly Clear",
        "partlycloudy":              "Partly Cloudy",
        "cloudy":                    "Cloudy",
        "fog":                       "Fog",
        "lightrain":                 "Light Rain",
        "rain":                      "Rain",
        "heavyrain":                 "Heavy Rain",
        "lightrainshowers":          "Light Rain Showers",
        "rainshowers":               "Rain Showers",
        "heavyrainshowers":          "Heavy Rain Showers",
        "lightsleet":                "Light Sleet",
        "sleet":                     "Sleet",
        "heavysleet":                "Heavy Sleet",
        "lightsleetshowers":         "Light Sleet Showers",
        "sleetshowers":              "Sleet Showers",
        "heavysleetshowers":         "Heavy Sleet Showers",
        "lightsnow":                 "Light Snow",
        "snow":                      "Snow",
        "heavysnow":                 "Heavy Snow",
        "lightsnowshowers":          "Light Snow Showers",
        "snowshowers":               "Snow Showers",
        "heavysnowshowers":          "Heavy Snow Showers",
        "thunder":                   "Thunderstorm",
        "thunderstorm":              "Thunderstorm",
        "lightrainandthunder":       "Thunderstorm with Light Rain",
        "rainandthunder":            "Thunderstorm with Rain",
        "heavyrainandthunder":       "Thunderstorm with Heavy Rain",
        "lightrainshowersandthunder":"Thunderstorm with Light Rain Showers",
        "rainshowersandthunder":     "Thunderstorm with Rain Showers",
        "heavyrainshowersandthunder":"Thunderstorm with Heavy Rain Showers",
        "lightsleetandthunder":      "Thunderstorm with Sleet",
        "sleetandthunder":           "Thunderstorm with Sleet",
        "lightsleetshowersandthunder":"Thunderstorm with Sleet Showers",
        "sleetshowersandthunder":    "Thunderstorm with Sleet Showers",
        "lightsnowandthunder":       "Thunderstorm with Snow",
        "snowandthunder":            "Thunderstorm with Snow",
        "lightsnowshowersandthunder":"Thunderstorm with Snow Showers",
        "snowshowersandthunder":     "Thunderstorm with Snow Showers",
    }

    def _met_symbol_to_desc(self, symbol_code: str) -> str:
        """Convert MET Norway symbol_code (e.g. 'rainshowers_night') to description."""
        # Strip day/night suffix: 'rainshowers_night' → 'rainshowers'
        base = symbol_code.split("_")[0].lower() if symbol_code else ""
        return self._MET_SYMBOL_MAP.get(base, symbol_code.replace("_", " ").title())

    def _fetch_combined_met_wttr(self) -> dict:
        """
        Combines:
        - MET Norway Locationforecast 2.0: precipitation_amount for the next hour
          (free, no key, most accurate free precip source confirmed live)
        - wttr.in: condition description and code (accurate for India, no key)

        Falls back gracefully if one of the two fails.
        """
        met_precip = None
        met_desc = None
        met_ok = False

        # --- MET Norway ---
        try:
            resp = requests.get(
                f"https://api.met.no/weatherapi/locationforecast/2.0/compact"
                f"?lat={self.lat}&lon={self.lon}",
                timeout=10,
                headers={"User-Agent": "UrbanFloodDigitalTwin/1.0 github.com/urbanfloodt"}
            )
            resp.raise_for_status()
            data = resp.json()
            series = data.get("properties", {}).get("timeseries", [])
            if series:
                now_utc = datetime.now(timezone.utc)
                # Find the closest time slot
                closest = min(
                    series,
                    key=lambda x: abs(
                        (datetime.fromisoformat(x["time"].replace("Z", "+00:00")) - now_utc)
                        .total_seconds()
                    )
                )
                instant = closest.get("data", {}).get("instant", {}).get("details", {})
                next1h = closest.get("data", {}).get("next_1_hours", {})

                met_precip = float(next1h.get("details", {}).get("precipitation_amount", 0.0))
                symbol = next1h.get("summary", {}).get("symbol_code", "")
                met_desc = self._met_symbol_to_desc(symbol) if symbol else None
                met_ok = True

                # Also grab instant details for temp/humidity/cloud
                met_temp = instant.get("air_temperature")
                met_humidity = instant.get("relative_humidity")
                met_cloud = instant.get("cloud_area_fraction")
        except Exception:
            met_ok = False

        # --- wttr.in (for accurate condition description + code) ---
        wttr_result = self._fetch_wttr_in()
        wttr_ok = wttr_result.get("source") not in ("error", None)

        if not met_ok and not wttr_ok:
            return {"source": "error", "description": "Both MET Norway and wttr.in failed"}

        # Prefer wttr.in description (more accurate for India conditions)
        # Use MET Norway precipitation (more accurate actual value)
        if wttr_ok and met_ok:
            return {
                "source": "met-norway + wttr.in",
                "temp_c": wttr_result.get("temp_c", met_temp),
                "precipitation_mm": met_precip,           # Real value from MET Norway
                "humidity": wttr_result.get("humidity", int(met_humidity) if met_humidity else None),
                "cloud_cover": wttr_result.get("cloud_cover", int(met_cloud) if met_cloud else None),
                "weather_code": wttr_result.get("weather_code"),
                "description": wttr_result.get("description"),  # wttr.in is more accurate for India
                "description_met": met_desc,              # MET Norway desc as secondary reference
            }
        elif wttr_ok:
            # MET Norway failed — use wttr.in alone (with floor estimate)
            return wttr_result
        else:
            # wttr.in failed — use MET Norway alone
            return {
                "source": "met-norway",
                "temp_c": met_temp,
                "precipitation_mm": met_precip,
                "humidity": int(met_humidity) if met_humidity else None,
                "cloud_cover": int(met_cloud) if met_cloud else None,
                "weather_code": None,
                "description": met_desc or "Unknown",
            }

    # ── wttr.in (standalone fallback) ────────────────────────────────────────

    # WWO precipitation floors — used ONLY when MET Norway is unavailable.
    # precipMM in wttr.in current_condition resets each measurement interval
    # and commonly reads 0.0 mid-storm. We substitute a conservative floor.
    # Ref: https://www.worldweatheronline.com/weather-api/api/docs/weather-icons.aspx
    _WWO_PRECIP_FLOOR = {
        389: 15.0,  # Thunderstorm with heavy rain
        386: 8.0,   # Thunderstorm with light/moderate rain
        392: 12.0,  # Thunderstorm with heavy snow (mixed)
        395: 10.0,  # Thunderstorm with heavy snow
        359: 20.0,  # Heavy rain
        356: 15.0,  # Moderate or heavy rain shower
        353: 5.0,   # Light rain shower
        308: 18.0,  # Heavy rain
        305: 12.0,  # Heavy rain at times
        302: 8.0,   # Moderate rain
        299: 6.0,   # Moderate rain at times
        296: 3.0,   # Light rain
        293: 2.0,   # Patchy light rain
        284: 3.0,   # Heavy freezing drizzle
        281: 2.0,   # Freezing drizzle
        266: 1.5,   # Light drizzle
        263: 1.0,   # Patchy light drizzle
        377: 10.0,  # Moderate or heavy sleet showers
        374: 4.0,   # Light sleet showers
        365: 10.0,  # Moderate or heavy sleet
        362: 3.0,   # Light sleet
        200: 8.0,   # Thundery outbreaks possible
    }

    def _fetch_wttr_in(self) -> dict:
        """
        wttr.in (WorldWeatherOnline) — good condition codes and descriptions.
        NOTE: precipMM resets per interval; _WWO_PRECIP_FLOOR applied when 0
        and MET Norway is unavailable.
        """
        try:
            url = f"https://wttr.in/{self.lat},{self.lon}?format=j1"
            resp = requests.get(url, timeout=10, headers={"User-Agent": "UrbanFloodDT/1.0"})
            resp.raise_for_status()
            data = resp.json()

            current = data.get("current_condition", [{}])[0]
            if not current:
                return {"source": "error", "description": "No current condition data from wttr.in"}

            temp = float(current.get("temp_C", 0))
            precip = float(current.get("precipMM", 0))
            humidity = int(current.get("humidity", 0))
            cloud_cover = int(current.get("cloudcover", 0))
            wwo_code = int(current.get("weatherCode", 0))

            weather_desc_list = current.get("weatherDesc", [])
            desc = weather_desc_list[0].get("value", "Unknown").strip() if weather_desc_list else "Unknown"

            # Apply floor only when used standalone (MET Norway unavailable)
            if precip == 0.0 and wwo_code in self._WWO_PRECIP_FLOOR:
                precip = self._WWO_PRECIP_FLOOR[wwo_code]

            return {
                "source": "wttr.in",
                "temp_c": temp,
                "precipitation_mm": precip,
                "humidity": humidity,
                "cloud_cover": cloud_cover,
                "weather_code": wwo_code,
                "description": desc,
            }
        except Exception as e:
            return {"source": "error", "description": f"wttr.in failed: {str(e)}"}

    # ── Open-Meteo (absolute last resort) ────────────────────────────────────

    def _fetch_open_meteo(self) -> dict:
        """
        Last-resort fallback: Open-Meteo NWP forecast model.
        WARNING: Confirmed to return weather_code=1 ("Mainly Clear") during an
        active thunderstorm in Bengaluru. Only used when all other sources fail.
        """
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={self.lat}&longitude={self.lon}"
                f"&current=temperature_2m,precipitation,rain,showers,weather_code,"
                f"cloudcover,relativehumidity_2m"
                f"&timezone=auto"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            current = data.get("current", {})
            temp = current.get("temperature_2m", 0)
            precip = current.get("precipitation", 0)
            rain = current.get("rain", 0)
            showers = current.get("showers", 0)
            total_precip = max(precip, rain + showers)
            wcode = current.get("weather_code", 0)

            desc = "Clear"
            if wcode == 1:              desc = "Mainly Clear"
            elif wcode == 2:            desc = "Partly Cloudy"
            elif wcode == 3:            desc = "Overcast"
            elif wcode in [45, 48]:     desc = "Fog"
            elif wcode in [51, 53, 55]: desc = "Drizzle"
            elif wcode in [56, 57]:     desc = "Freezing Drizzle"
            elif wcode in [61, 63, 65]: desc = "Rain"
            elif wcode in [66, 67]:     desc = "Freezing Rain"
            elif wcode in [71, 73, 75, 77]: desc = "Snow"
            elif wcode in [80, 81, 82]: desc = "Rain Showers"
            elif wcode in [85, 86]:     desc = "Snow Showers"
            elif wcode == 95:           desc = "Thunderstorm"
            elif wcode in [96, 99]:     desc = "Thunderstorm with Hail"

            return {
                "source": "open-meteo (last resort)",
                "temp_c": temp,
                "precipitation_mm": total_precip,
                "humidity": current.get("relativehumidity_2m"),
                "cloud_cover": current.get("cloudcover"),
                "weather_code": wcode,
                "description": desc,
            }
        except Exception as e:
            return {"source": "error", "description": str(e)}
