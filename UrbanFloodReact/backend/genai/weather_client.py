import requests

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
        Fetch current weather using wttr.in (primary) with Open-Meteo fallback.
        
        wttr.in uses WorldWeatherOnline data which aggregates actual weather
        station observations — significantly more accurate for real-time
        conditions in India compared to Open-Meteo's forecast models.
        """
        # Try wttr.in first (more accurate real-time data for India)
        result = self._fetch_wttr_in()
        if result and result.get("source") != "error":
            return result
        
        # Fallback to Open-Meteo
        return self._fetch_open_meteo()
    
    def _fetch_wttr_in(self) -> dict:
        """
        Fetch current weather from wttr.in (backed by WorldWeatherOnline).
        Uses lat,lon coordinates for precise location matching.
        Returns actual observed weather rather than model forecasts.
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
            
            # Get the human-readable weather description
            weather_desc_list = current.get("weatherDesc", [])
            desc = weather_desc_list[0].get("value", "Unknown").strip() if weather_desc_list else "Unknown"
            
            # WWO weather code for reference
            wwo_code = int(current.get("weatherCode", 0))
            
            return {
                "source": "wttr.in",
                "temp_c": temp,
                "precipitation_mm": precip,
                "humidity": humidity,
                "cloud_cover": cloud_cover,
                "weather_code": wwo_code,
                "description": desc
            }
        except Exception as e:
            return {"source": "error", "description": f"wttr.in failed: {str(e)}"}
    
    def _fetch_open_meteo(self) -> dict:
        """
        Fallback: Fetch current weather from Open-Meteo.
        Note: Open-Meteo uses forecast models which can miss real-time
        convective rainfall events, especially in tropical regions like India.
        """
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={self.lat}&longitude={self.lon}"
                f"&current=temperature_2m,precipitation,rain,showers,weather_code"
                f"&timezone=auto"
            )
            
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            current = data.get("current", {})
            temp = current.get("temperature_2m", 0)
            # Sum all precipitation fields for better detection
            precip = current.get("precipitation", 0)
            rain = current.get("rain", 0)
            showers = current.get("showers", 0)
            total_precip = max(precip, rain + showers)
            
            wcode = current.get("weather_code", 0)
            
            # Corrected WMO Weather interpretation code mapping
            # See: https://open-meteo.com/en/docs (WMO Weather interpretation codes)
            desc = "Clear"
            if wcode == 1: desc = "Mainly Clear"
            elif wcode == 2: desc = "Partly Cloudy"
            elif wcode == 3: desc = "Overcast"
            elif wcode in [45, 48]: desc = "Fog"
            elif wcode in [51, 53, 55]: desc = "Drizzle"
            elif wcode in [56, 57]: desc = "Freezing Drizzle"
            elif wcode in [61, 63, 65]: desc = "Rain"
            elif wcode in [66, 67]: desc = "Freezing Rain"
            elif wcode in [71, 73, 75, 77]: desc = "Snow"
            elif wcode in [80, 81, 82]: desc = "Rain Showers"
            elif wcode in [85, 86]: desc = "Snow Showers"
            elif wcode == 95: desc = "Thunderstorm"
            elif wcode in [96, 99]: desc = "Thunderstorm with Hail"
            
            return {
                "source": "open-meteo",
                "temp_c": temp,
                "precipitation_mm": total_precip,
                "weather_code": wcode,
                "description": desc
            }
        except Exception as e:
            return {
                "source": "error",
                "description": str(e)
            }
