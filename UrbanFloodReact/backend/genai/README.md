# GenAI Module - Urban Flood Evacuation System

This directory contains the Generative AI (GenAI) integration scripts that power the intelligent advisory and data retrieval functionality of the Digital Twin-Driven Flood Evacuation System.

## Overview of Components

### 1. Panel of Experts (`expert_panel.py`)
This script handles the streaming of actionable intelligence from three distinct AI personas:
- **Logistics Chief**: Analyzes shelter capacity and proposes concrete resource allocation and evacuee transfer plans.
- **Tactical Commander**: Inspects evacuation routes and issues tactical instructions for deploying NDRF personnel, lifeboats, and traffic management.
- **Civic Authority**: Generates standardized government situation reports and drafts succinct SMS/Social media warnings for public broadcast.

**Key Features:**
- **Strict Constraints:** Each persona is strictly instructed not to explain its reasoning or summarize the input data, providing only the highly structured, actionable output.
- **Groq API Integration:** By default, the system utilizes the lightning-fast Groq API (model: `llama-3.1-8b-instant`) to generate responses, dramatically reducing local system load and RAM usage.
- **Local Ollama Fallback:** If the Groq API key is missing or the external API fails, the system automatically falls back to a local robust offline `llama3.2:latest` instance.

### 2. MCP Weather Integration (`mcp_weather_server.py` & `mcp_weather_client.py`)
These scripts fetch real-time weather information using the Model Context Protocol (MCP).

- **`mcp_weather_client.py`**: A client script that resolves "Hobli" text names to their latitude/longitude coordinates (via `param_resolver.py`), connects to the official prebuilt Anthropic weather server (`@modelcontextprotocol/server-weather`) using standard I/O (stdio), and fetches live temperature and precipitation alerts.
- **`mcp_weather_server.py`**: A FastMCP server wrapper meant to expose `get_current_weather` as a tool for other AI agents using the standard `WeatherClient`. 

## Setup Instructions

1. **Environment Variables**: Make sure your `.env` file at the project root contains your Groq API key to utilize the cloud reasoning:
   ```env
   GROQ_API_KEY=your_key_here
   ```
2. **Offline Fallback**: Ensure that you have Ollama installed locally with the `llama3.2:latest` model pulled if you expect to run completely offline.
3. **MCP Requirements**: Ensure `npx` (Node Package Manager) is installed, as `mcp_weather_client.py` uses `npx -y @modelcontextprotocol/server-weather` dynamically to fetch live data.
