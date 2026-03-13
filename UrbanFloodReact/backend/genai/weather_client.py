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
        Fetch current weather from Open-Meteo.
        Provides temperature and precipitation.
        """
        try:
            # We use Open-Meteo's current API for temperature and precipitation
            url = f"https://api.open-meteo.com/v1/forecast?latitude={self.lat}&longitude={self.lon}&current=temperature_2m,precipitation,weather_code"
            
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            current = data.get("current", {})
            temp = current.get("temperature_2m", 0)
            precip = current.get("precipitation", 0)
            wcode = current.get("weather_code", 0)
            
            # Simple WMO Weather interpretation code mapping
            desc = "Clear"
            if wcode in [1, 2, 3]: desc = "Partly Cloudy"
            elif wcode in [45, 48]: desc = "Fog"
            elif wcode in [51, 53, 55, 56, 57]: desc = "Drizzle"
            elif wcode in [61, 63, 65, 66, 67]: desc = "Rain"
            elif wcode in [71, 73, 75, 77]: desc = "Snow"
            elif wcode in [80, 81, 82]: desc = "Rain Showers"
            elif wcode >= 95: desc = "Thunderstorm"
            
            return {
                "source": "open-meteo",
                "temp_c": temp,
                "precipitation_mm": precip,
                "weather_code": wcode,
                "description": desc
            }
        except Exception as e:
            return {
                "source": "error",
                "description": str(e)
            }
