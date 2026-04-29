#!/usr/bin/env python3
"""
Test runner for MCP vs non-MCP evaluation with sample data.
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

# Mock enriched context (simplified version)
MOCK_CONTEXT = {
    "simulation": {
        "total_population": 50000,
        "evacuated": 35000,
        "cannot_evacuate": 15000,
    },
    "shelters": [
        {"name": "City Hall Shelter", "capacity": 5000, "occupancy": 4800, "risk": "high"},
        {"name": "Stadium Shelter", "capacity": 10000, "occupancy": 8500, "risk": "medium"},
        {"name": "School Shelter", "capacity": 3000, "occupancy": 2900, "risk": "high"},
    ],
    "roads": [
        {"name": "Main Street", "severity": "blocked", "vehicles_stuck": 120},
        {"name": "Highway 101", "severity": "congested", "vehicles_stuck": 45},
    ],
    "transit": {
        "bus_stops_affected": 12,
        "metro_lines_disrupted": 3,
        "buses_operational": 5,
    },
    "rescue": {
        "ndrf_teams": 2,
        "unmet_rescue_needs": 150,
    }
}

SAMPLE_QUESTIONS = [
    "Which shelter is most at risk of overflow?",
    "What is the safest evacuation route?",
]

async def test_mcp_vs_nonmcp():
    """Test both evaluation paths."""
    print("=" * 70)
    print("MCP vs Non-MCP Evaluation Test")
    print("=" * 70)
    
    try:
        from genai.mcp_evaluator import compare_one, DEFAULT_QUESTIONS
        from genai.non_mcp_chat import analyze_no_mcp
        from genai.mcp_chat_metrics import analyze_with_mcp
        
        print("\n[OK] All imports successful\n")
        
        # Test with first sample question
        question = SAMPLE_QUESTIONS[0]
        print(f"Testing question: '{question}'")
        print("-" * 70)
        
        print("\n[1/2] Running Non-MCP approach...")
        try:
            non_mcp_result = await analyze_no_mcp(question, MOCK_CONTEXT)
            print(f"[OK] Non-MCP completed")
            print(f"  - Model used: {non_mcp_result.get('model_used', 'unknown')}")
            print(f"  - Response length: {len(non_mcp_result.get('response_text', ''))} chars")
            if non_mcp_result.get('response_text'):
                print(f"  - Preview: {non_mcp_result['response_text'][:150]}...")
        except Exception as e:
            print(f"[FAIL] Non-MCP failed: {e}")
            non_mcp_result = None
        
        print("\n[2/2] Running MCP approach...")
        try:
            mcp_result = await analyze_with_mcp(question, MOCK_CONTEXT)
            print(f"[OK] MCP completed")
            print(f"  - Response length: {len(mcp_result.get('response_text', ''))} chars")
            print(f"  - Tool calls: {len(mcp_result.get('tool_calls', []))} calls")
            if mcp_result.get('error'):
                print(f"  - Error: {mcp_result['error']}")
            if mcp_result.get('tool_calls'):
                for i, tool_call in enumerate(mcp_result['tool_calls'], 1):
                    print(f"    [{i}] {tool_call['name']}() -> {tool_call['result_preview'][:80]}...")
            if mcp_result.get('response_text'):
                print(f"  - Preview: {mcp_result['response_text'][:150]}...")
        except Exception as e:
            print(f"[FAIL] MCP failed: {e}")
            import traceback
            traceback.print_exc()
            mcp_result = None
        
        print("\n" + "=" * 70)
        print("Comparison Results")
        print("=" * 70)
        
        if non_mcp_result and mcp_result:
            print("\n[OK] Both approaches completed successfully!")
            print("\nKey Metrics:")
            print(f"  Non-MCP response length: {len(non_mcp_result.get('response_text', ''))} chars")
            print(f"  MCP response length: {len(mcp_result.get('response_text', ''))} chars")
            
            if 'tool_calls' in mcp_result:
                num_tools = len(mcp_result['tool_calls'])
                print(f"  MCP tool calls: {num_tools}")
                if num_tools >= 2:
                    print(f"    [OK] Multi-tool chaining met (>=2 calls)")
                else:
                    print(f"    [WARN] Multi-tool chaining not met (<2 calls)")
            
            # Check for specific content
            mcp_text = mcp_result.get('response_text', '').lower()
            non_mcp_text = non_mcp_result.get('response_text', '').lower()
            
            print(f"\n  MCP mentions shelters: {'city hall' in mcp_text or 'stadium' in mcp_text}")
            print(f"  Non-MCP mentions shelters: {'city hall' in non_mcp_text or 'stadium' in non_mcp_text}")
            
        else:
            print("\n[WARN] One or both approaches failed. Check API keys and setup.")
        
    except Exception as e:
        print(f"\n[FAIL] Critical error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_mcp_vs_nonmcp())
