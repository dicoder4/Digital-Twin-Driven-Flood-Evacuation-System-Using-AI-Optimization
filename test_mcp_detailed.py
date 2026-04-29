#!/usr/bin/env python3
"""
Detailed debug test for MCP evaluation.
"""
import sys
import os
import asyncio
import json
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = os.path.join(os.path.dirname(__file__), 'UrbanFloodReact/backend/.env')
load_dotenv(env_path)

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'UrbanFloodReact/backend'))

MOCK_CONTEXT = {
    "simulation": {
        "location": "Beguru, Karnataka",
        "algorithm": "GA",
        "success_rate_pct": 89.5,
        "total_evacuated": 35000,
        "total_at_risk_remaining": 15000,
        "execution_time_s": 12.5,
    },
    "shelters": [
        {"name": "City Hall Shelter", "capacity": 5000, "occupancy": 4800},
        {"name": "Stadium Shelter", "capacity": 10000, "occupancy": 8500},
    ],
}

async def test_mcp_detailed():
    """Test MCP with detailed output."""
    from genai.mcp_chat_metrics import analyze_with_mcp
    
    question = "Which shelter is most at risk of overflow?"
    
    print("Testing MCP approach with detailed output...")
    print("=" * 70)
    
    result = await analyze_with_mcp(question, MOCK_CONTEXT)
    
    print(f"\nResult structure:")
    for key, val in result.items():
        if key == "tool_calls" and val:
            print(f"  {key}: [{len(val)} calls]")
            for tool in val:
                print(f"    - {tool['name']}({tool['args']})")
        elif key == "response_text":
            if val:
                print(f"  {key}: {len(val)} chars - '{val[:100]}...'")
            else:
                print(f"  {key}: EMPTY!")
        else:
            print(f"  {key}: {val}")

if __name__ == "__main__":
    asyncio.run(test_mcp_detailed())
