from mcp.server.fastmcp import FastMCP
from param_resolver import resolve_hobli
from weather_client import WeatherClient

# Create an MCP server named "Urban Flood Weather Server"
mcp = FastMCP("Urban Flood Weather Server")

@mcp.tool()
def get_current_weather(hobli_name: str) -> str:
    """
    Fetch the current real-time rainfall and weather data for a given Hobli in Bengaluru.
    
    Args:
        hobli_name: The name of the Hobli (e.g. "Begur", "Yelahanka", "Varthur")
    """
    info = resolve_hobli(hobli_name)
    if not info:
        return f"Error: Could not find coordinates for Hobli '{hobli_name}'."
        
    client = WeatherClient.from_hobli_info(info)
    data = client.get_current()
    
    if data.get("source") == "error":
        return f"Error fetching weather: {data.get('description')}"
        
    return (
        f"Weather for {info['display']}:\n"
        f"Temperature: {data['temp_c']}°C\n"
        f"Rainfall: {data['precipitation_mm']} mm\n"
        f"Condition: {data['description']}"
    )

if __name__ == "__main__":
    mcp.run()
