import sys, re
sys.path.insert(0, r'c:/College/major project/Digital-Twin-Driven-Flood-Evacuation-System-Using-AI-Optimization/UrbanFloodReact/backend')

# Copy _classify_intent from mcp_pipeline.py to test it standalone
def _classify_intent(message):
    m = message.lower()
    sim_kws   = ["simulat", "run", "trigger", "flood", "evacuat", "model", "predict"]
    wx_kws    = ["weather", "rain", "rainfall", "precipitation", "forecast", "climate"]
    stat_kws  = ["result", "status", "how many", "evacuated", "summary", "report"]

    sim_score  = sum(1 for k in sim_kws  if k in m)
    wx_score   = sum(1 for k in wx_kws   if k in m)
    stat_score = sum(1 for k in stat_kws if k in m)

    if sim_score >= 1 and sim_score >= wx_score:
        return "simulation_request"
    if wx_score >= 2:
        return "weather_query"
    if stat_score >= 2:
        return "status_query"
    return "general"

test_messages = [
    "simulate uttarahalli",
    "run flood simulation for sarjapura",
    "flood simulation for BTM",
    "simulate marathahalli",
    "simulate sarjapura-1",
    "Run a flood simulation",
    "what is the rainfall in yelahanka",
    "yes",
    "1",
    "historical",
]

print("=== _classify_intent ===")
for msg in test_messages:
    intent = _classify_intent(msg)
    print(f"  {msg!r:45} -> {intent}")
