import asyncio
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
import sys
import os

from param_resolver import resolve_hobli

async def main():
    if len(sys.argv) < 2:
        print("Usage: python mcp_weather_client.py <hobli_name>")
        return

    hobli_name = sys.argv[1]
    info = resolve_hobli(hobli_name)
    if not info:
        print(f"Error: Could not find coordinates for Hobli '{hobli_name}'.")
        return
        
    lat = info["lat"]
    lon = info["lon"]
    
    print(f"Connecting to prebuilt MCP weather server for {info['display']} ({lat}, {lon})...")
    
    # We use the prebuilt MCP weather server via NPX
    # The official Anthropic server is @modelcontextprotocol/server-weather
    server_params = StdioServerParameters(
        command="npx.cmd" if os.name == "nt" else "npx",
        args=["-y", "@modelcontextprotocol/server-weather"],
        env=None
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                print("Connected! Fetching current weather forecast (get-forecast)...")
                try:
                    result = await session.call_tool("get-forecast", arguments={"latitude": lat, "longitude": lon})
                    print("\n--- Weather Forecast Result ---")
                    for content in result.content:
                        if content.type == "text":
                            print(content.text)
                except Exception as eval_err:
                    print(f"Error calling get-forecast tool: {eval_err}")
                    
                print("\nFetching weather alerts (get-alerts)...")
                try:
                    alerts_result = await session.call_tool("get-alerts", arguments={"state": "CA"}) # Just an example if NWS requires state code
                    print("\n--- Weather Alerts Result ---")
                    for content in alerts_result.content:
                        if content.type == "text":
                            print(content.text)
                except Exception as e:
                    pass

    except Exception as e:
        print(f"Failed to connect to MCP server or fetch weather: {e}")
        print("Note: The official @modelcontextprotocol/server-weather uses NWS data, which only supports US coordinates.")

if __name__ == "__main__":
    asyncio.run(main())
