#!/usr/bin/env python3
"""
Quick test to verify the fixes to mcp_chat_metrics and non_mcp_chat.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'UrbanFloodReact/backend'))

# Test 1: Check if mcp_chat_metrics.py has the updated SYSTEM_PROMPT
print("=" * 60)
print("TEST 1: Checking mcp_chat_metrics.py SYSTEM_PROMPT")
print("=" * 60)
try:
    from genai.mcp_chat_metrics import SYSTEM_PROMPT
    if "CRITICAL TOOL ROUTING HINTS" in SYSTEM_PROMPT:
        print("✓ Tool routing hints found in SYSTEM_PROMPT")
    else:
        print("✗ Tool routing hints NOT found in SYSTEM_PROMPT")
    
    if "Make at least 2-3 tool calls" in SYSTEM_PROMPT:
        print("✓ Multi-tool chaining constraint found")
    else:
        print("✗ Multi-tool chaining constraint NOT found")
        
    if "get_simulation_state()" in SYSTEM_PROMPT:
        print("✓ get_simulation_state() routing instruction found")
    else:
        print("✗ get_simulation_state() routing instruction NOT found")
        
    print("\nSYSTEM_PROMPT excerpt:")
    print(SYSTEM_PROMPT[:500] + "...\n")
except Exception as e:
    print(f"✗ Error importing mcp_chat_metrics: {e}")

# Test 2: Check if non_mcp_chat.py has Groq fallback
print("=" * 60)
print("TEST 2: Checking non_mcp_chat.py for Groq fallback")
print("=" * 60)
try:
    with open('UrbanFloodReact/backend/genai/non_mcp_chat.py', 'r') as f:
        content = f.read()
    
    if 'from groq import Groq' in content:
        print("✓ Groq import found")
    else:
        print("✗ Groq import NOT found")
    
    if 'groq_client' in content:
        print("✓ Groq client initialization found")
    else:
        print("✗ Groq client initialization NOT found")
    
    if 'llama-3.3-70b-versatile' in content:
        print("✓ Groq model specification found")
    else:
        print("✗ Groq model specification NOT found")
        
    if 'except Exception as e:' in content and 'Groq' in content:
        print("✓ Groq fallback error handling found")
    else:
        print("✗ Groq fallback error handling NOT found")
        
except Exception as e:
    print(f"✗ Error checking non_mcp_chat.py: {e}")

print("\n" + "=" * 60)
print("TEST 3: Basic imports check")
print("=" * 60)
try:
    from genai.non_mcp_chat import analyze_no_mcp
    print("✓ analyze_no_mcp imported successfully")
except Exception as e:
    print(f"✗ Failed to import analyze_no_mcp: {e}")

try:
    from genai.mcp_chat_metrics import analyze_with_mcp
    print("✓ analyze_with_mcp imported successfully")
except Exception as e:
    print(f"✗ Failed to import analyze_with_mcp: {e}")

print("\n" + "=" * 60)
print("All tests completed!")
print("=" * 60)
