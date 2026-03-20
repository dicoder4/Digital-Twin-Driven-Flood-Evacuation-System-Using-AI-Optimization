import httpx
import sys
import os
import asyncio

# Add parent directory for imports if run as script
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genai.param_resolver import resolve_hobli

class WeatherClient:
    """
    Consolidated Weather Client for the Urban Flood system.
    Provides real-time weather data using Open-Meteo, which supports global coordinates.
    """
    def __init__(self, lat: float, lon: float):
        self.lat = lat
        self.lon = lon
    
    @classmethod
    def from_hobli_info(cls, info: dict):
        if not info or "lat" not in info:
            raise ValueError("Invalid hobli info provided to WeatherClient")
        return cls(info["lat"], info["lon"])
        
    def get_current(self) -> dict:
        """
        Fetch current weather parameters.
        Returns a dict with temp_c, precipitation_mm, and description.
        """
        url = f"https://api.open-meteo.com/v1/forecast?latitude={self.lat}&longitude={self.lon}&current=temperature_2m,precipitation&timezone=auto"
        try:
            # Note: Using httpx.get (sync) to maintain compatibility with existing sync backend paths
            resp = httpx.get(url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            curr = data.get("current", {})
            return {
                "temp_c": curr.get("temperature_2m", 25),
                "precipitation_mm": curr.get("precipitation", 0),
                "description": "Live data from Open-Meteo",
                "source": "open-meteo"
            }
        except Exception as e:
            return {
                "source": "error",
                "description": f"Failed to fetch weather: {str(e)}",
                "temp_c": 25,
                "precipitation_mm": 0
            }

async def fetch_weather_mcp_style(hobli_name: str):
    """Async helper for MCP tools or async endpoints."""
    info = resolve_hobli(hobli_name)
    if not info:
        return {"error": f"Region {hobli_name} not found"}
    
    client = WeatherClient.from_hobli_info(info)
    # Since get_current is currently sync, we wrap it or just call it
    return client.get_current()

if __name__ == "__main__":
    # Test CLI usage
    if len(sys.argv) > 1:
        res = asyncio.run(fetch_weather_mcp_style(sys.argv[1]))
        print(f"Weather for {sys.argv[1]}: {res}")
    else:
        print("Usage: python mcp_weather_client.py <hobli_name>")
