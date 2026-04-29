# MCP vs Non-MCP GenAI Comparison
## Implementation Plan & Progress

---

## What Are We Doing and Why?

Our system uses GenAI (Google Gemini) to answer questions about the flood evacuation
simulation — things like "which shelter is overflowing?", "which roads are bottlenecks?",
"are there buses near the flood zone?".

There are two ways to give an AI the data it needs to answer these questions:

**Non-MCP (baseline):** Dump everything into one big prompt upfront — shelter occupancy,
route details, road conditions, terrain, metro status, rescue guidelines, all of it.
The AI reads the entire wall of text and picks out what it needs. Like handing someone
a 150-page briefing and asking them to find the answer.

**MCP (our system):** Give the AI a tiny summary (just 6 fields, ~80 words) and a
toolkit of functions it can call on demand. It calls `get_shelter_status()` to see
shelter occupancy, `analyze_road_conditions()` to find bottlenecks, `check_bus_availability(lat, lon)`
to find nearby buses, etc. Like a doctor who orders the specific tests they need
rather than reading the entire patient history upfront.

We are building a rigorous A/B comparison between these two modes to show — with
numbers — which approach produces better answers for disaster response. This goes
into the research paper.

---

## The One Variable We Are Testing

**Everything is held constant:**
- Same AI model (Gemini 2.5 Flash)
- Same simulation data (same flood state, same shelters, same routes)
- Same 8 questions
- Same scoring rubric

**The only thing that changes:** how the AI retrieves the data.

| | MCP | Non-MCP |
|---|---|---|
| Seed given to AI | 80 words (simulation summary only) | 7,600 words (full data dump) |
| How AI gets shelter details | Calls `get_shelter_status()` tool | Already in the dump |
| How AI gets road conditions | Calls `analyze_road_conditions()` tool | Already in the dump |
| How AI gets bus availability | Calls `check_bus_availability(lat, lon)` tool | **Cannot — not in dump** |
| How AI gets transit disruptions | Calls `analyze_transit_disruptions()` tool | **Cannot — not in dump** |
| Hallucination risk | Lower — fetches only what it needs | Higher — overwhelmed by data |

The last two rows are the most important for the paper: bus availability and transit
disruptions are **live, coordinate-dependent data** that cannot be pre-dumped.
Only the MCP arm can answer those questions at all.

---

## What Tools Does the MCP Arm Have?

The MCP arm (with tools) can call any of these on demand:

| Tool | What it returns |
|------|----------------|
| `get_simulation_state()` | High-level summary: algorithm, success rate, total evacuated |
| `get_shelter_status()` | Full occupancy table: name, capacity, % full, status (CRITICAL/HIGH/MODERATE) |
| `get_route_summary()` | Route stats: total routes, avg/max distance, largest group |
| `get_terrain_analysis()` | Min/avg/max elevation, total relief range |
| `analyze_road_conditions(road_name)` | Top bottleneck junctions with flood depth and evacuee volume |
| `get_rescue_guidelines()` | NDRF protocols for people who could not be routed |
| `narrate_best_route(shelter_name)` | The lowest-distance route to a specific shelter |
| `get_metro_status()` | Line-by-line Bengaluru metro health (safe/caution/unsafe stations) |
| `get_flood_impact()` | Socio-economic impact summary |
| `get_shelter_resource_map()` | Resources available at each shelter |
| `get_vulnerability_hotspots()` | High-risk population clusters |
| `check_bus_availability(lat, lon)` | Nearest bus stop and routes at a coordinate |
| `analyze_transit_disruptions(location, depth)` | Which BMTC routes are disabled by flood |

The Non-MCP arm calls **none of these** — everything must come from the static dump.

---

## The 8 Test Questions

These are the same questions run through both arms on every simulation scenario:

1. Which shelter is most at risk of overflow and what should we do about it?
2. What is the safest evacuation route from the most flooded zone?
3. How many people cannot be evacuated and why?
4. Which roads are critical bottlenecks and how should NDRF approach them?
5. Are there bus stops near the flooded zones that can support evacuation?
6. Which transit routes will be disabled by the current flood?
7. What are the unmet rescue needs, and who should we escalate to?
8. Give me an overall situation report I can hand to the District Commissioner.

**Questions 5 and 6** are the most differentiating — non-MCP physically cannot answer
them because bus/transit data requires live coordinate lookups.

---

## How We Score the Responses

### Auto-Measurable (no human needed)

| Metric | What it measures |
|--------|----------------|
| `prompt_words` | Size of what was sent to the AI |
| `response_words` | Length of the AI's answer |
| `latency_s` | How long the AI took to respond |
| `tool_call_count` | How many tools the MCP arm called |
| `tools_used` | Which specific tools were called, in order |
| `shelter_name_match_count` | How many real shelter names from the simulation appear in the response |
| `numeric_match_rate` | Fraction of numbers cited that match actual simulation data (0.0–1.0) |
| `suspicious_capitalised` | Heuristic flag for invented proper nouns (hallucination signal) |

### LLM-Judge Rubric (Gemini or Groq scores each response 1–5, blind)

The judge does not know which mode (MCP or non-MCP) produced the response.
It receives the simulation ground truth + the question + the response, and scores:

| Dimension | Score 1 | Score 5 |
|-----------|---------|---------|
| **Accuracy** | Cites wrong shelter names or numbers | All data exactly matches simulation |
| **Specificity** | Generic boilerplate ("coordinate with authorities") | Names specific nodes, roads, shelter IDs |
| **Actionability** | An NDRF officer cannot act on this | Immediate operational action is possible |
| **Hallucination severity** | Severely fabricated entities invented | Zero hallucinations detected |

**Provider:** Gemini 2.5 Flash (primary) → Groq llama-3.3-70b (fallback when Gemini
hits its 20 request/day free-tier quota). The `provider` field in results shows which
judge was used.

---

## Experimental Design

**Sample:** 3 simulation scenarios × 8 questions = **48 paired comparisons**

| Scenario | Flood intensity | Hobli |
|----------|----------------|-------|
| S1 | Low (30mm rainfall) | Beguru-1 |
| S2 | Medium (60mm rainfall) | Beguru-1 |
| S3 | High (100mm rainfall) | Beguru-1 |

Same Hobli across all scenarios so the road graph, shelters, and population are identical.
Only the flood depth changes, which changes which roads are blocked and which shelters
are at risk. This gives us the most controlled comparison possible.

---

## Implementation: What Was Built

### Phase 1 — Backend (Done)

#### `genai/non_mcp_chat.py` — the Non-MCP arm

Before calling Gemini, this file:
1. Calls every parameter-less MCP tool directly and concatenates their text output
2. Strips `local_inventory` from the simulation context (200 fire-station supply items
   that caused hallucinations by confusing supply sources with shelter destinations)
3. Builds one big prompt: cleaned simulation context + materialized tool outputs
4. Sends to Gemini with **no tools** — the model cannot make any tool calls
5. Falls back to Groq `llama-3.3-70b-versatile` if Gemini hits quota or API errors

Returns: response text, prompt word count, response word count, latency, token usage.

**Why strip `local_inventory`?**
The enriched context contains 200 entries like `"SOUTH FIRE STATION — Slotted
Screwdrivers 4 Nos at 0.8km"`. These are supply sources for the logistics expert
panel, not relevant to Q&A. Without stripping, the model fabricated shelter
recommendations citing "State Disaster Response Force A Company — Tent Store" —
a classic prompt-stuffing hallucination. After stripping: judge scores improved
from 2/5 to 4–5/5 across dimensions.

---

#### `genai/mcp_chat_metrics.py` — the MCP arm

Sends only a **minimal seed** (6 simulation summary fields, ~80 words) to Gemini,
then runs a tool-execution loop — similar to the production `evacuation_chat.py`
chat flow — but non-streaming and metric-capturing.

Records every tool call:
```
{ "name": "get_shelter_status", "args": {}, "result_preview": "=== Shelter Status Report ===..." }
```

Returns: response text, prompt/response counts, latency, full `tool_calls` log.

If Gemini raises a 429 quota error or any other generation failure, this file now
falls back to Groq so the research run can continue.

**Why minimal seed instead of full context?**
When we initially gave MCP the full enriched context (140 shelters inline), Gemini
found all the answers in the prompt and never called a single tool — making MCP
functionally identical to non-MCP. The minimal seed forces genuine tool use.

**Production chat is untouched.** `evacuation_chat.py` still streams to the frontend
normally. This file is a separate research-only variant.

---

#### `genai/mcp_evaluator.py` — the comparison harness

- `compare_one(question, enriched_context)` — runs both arms in parallel via
  `asyncio.gather`, then scores both responses
- `compare_many(questions, enriched_context)` — loops over a list of questions
- `llm_judge(question, response, enriched_context)` — Gemini primary, Groq fallback,
  returns `{accuracy, specificity, actionability, hallucination_severity, reason, provider}`
- `DEFAULT_QUESTIONS` — the 8-question bank above
- `_auto_metrics(response, context)` — computes shelter matches, numeric accuracy, suspicious phrases

The harness now works even when Gemini is rate-limited, because the primary
generation paths and the judge both have Groq fallback behavior.

---

#### Validation helpers added

- `test_mcp_comparison.py` — runs a one-question side-by-side comparison and prints summary metrics
- `test_mcp_detailed.py` — prints the full MCP result structure, including tool trace and error state
- `validate_fixes.py` — checks that the three high-priority fixes are present in the codebase

---

## Current Test Results

**Setup used in validation:** `Beguru-1` sample context, Gemini primary with Groq fallback enabled, Windows PowerShell.

### What the latest runs show

| Metric | Non-MCP | MCP |
|--------|---------|-----|
| Prompt size | Large static dump | Minimal seed |
| Tool calls | `0` | `2` in the detailed MCP test |
| Gemini quota handling | Falls back to Groq | Falls back to Groq |
| Response quality | Good for broad factual lookup | Good for tool-grounded lookup |
| Live data reach | Limited to preloaded dump | Can fetch live tool outputs |

### Observed behavior

- The **Non-MCP** arm now returns a valid response even when Gemini hits quota, because Groq fallback is active.
- The **MCP** arm now returns a valid response even when Gemini hits quota, because Groq fallback is also active.
- The detailed MCP test confirmed real tool tracing via `tool_calls`.
- For question types that depend on live or coordinate-specific retrieval, MCP remains the stronger design.

---

## Issues Encountered and How They Were Fixed

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| MCP initially called zero tools | Full enriched context gave Gemini all answers inline | Switched to a minimal seed so tools must be called |
| Non-MCP hallucinated supply sources as shelters | `local_inventory` (200 fire-station items) confused the model | Strip `local_inventory` from the baseline prompt |
| Gemini quota errors stopped runs | Free-tier 429 rate limits on `gemini-2.5-flash` | Added Groq fallback to the generation paths and judge |
| Tool trace was mislabeled in tests | The test script looked for `tools_called` instead of `tool_calls` | Updated the test script to read the real field |
| Windows console failed on Unicode symbols | PowerShell `cp1252` output could not render checkmarks | Switched test output to ASCII-safe labels |

---

## The Research Claim
> *"MCP-enabled GenAI agents are better suited for live, location-specific, or
> tool-dependent flood-evacuation questions, while static-dump prompting remains
> competitive for broad factual summaries that can be answered from preloaded data.
> The strongest design is question-type-aware retrieval: use MCP when live lookup is
> needed, and use static prompts when the answer is already fully available."*

This framing is more defensible than a blanket “MCP is better” claim because it
identifies where each approach performs best.

---

## How To Run

### 1) Activate the virtual environment

```powershell
cd C:\Users\Diya\Digital-Twin-Driven-Flood-Evacuation-System-Using-AI-Optimization
& .\.venv\Scripts\Activate.ps1
```

### 2) Ensure `.env` is loaded

The validation scripts read `UrbanFloodReact/backend/.env` automatically, so no manual export is usually needed. Make sure the file contains:

- `GEMINI_API_KEY`
- `GROQ_API_KEY`
- `MONGO_URI` and any other required backend values

### 3) Run the comparison test

```powershell
python test_mcp_comparison.py
```

This prints:
- Non-MCP response length and preview
- MCP response length
- MCP `tool_calls` count and trace
- Any Gemini/Groq error state

### 4) Run the detailed MCP trace

```powershell
python test_mcp_detailed.py
```

Use this when you want to inspect the exact tools called and confirm the response body.

### 5) Validate the implemented fixes

```powershell
python validate_fixes.py
```

This checks:
- prompt-routing hints in `mcp_chat_metrics.py`
- Groq fallback in `non_mcp_chat.py`
- Groq fallback in `mcp_chat_metrics.py`

### 6) Optional: capture output to a file

```powershell
python test_mcp_comparison.py 2>&1 > test_output.txt
Get-Content test_output.txt -Tail 60
```

---

## How To Test

- **Quick smoke test:** run `python validate_fixes.py`
- **Functional test:** run `python test_mcp_comparison.py`
- **Deep trace test:** run `python test_mcp_detailed.py`
- **Success criteria:** both arms return a response, MCP logs at least one or more tool calls, and Groq fallback prevents quota failures from stopping the run

---

## File Map

```
UrbanFloodReact/backend/
└── genai/
    ├── non_mcp_chat.py                  ← baseline arm with Groq fallback
    ├── mcp_chat_metrics.py              ← MCP arm with metrics capture + Groq fallback
    ├── mcp_evaluator.py                 ← comparison harness + LLM judge (Gemini→Groq fallback)
    ├── mcp_evacuation_server.py         ← existing, unchanged
    ├── mcp_flood_intelligence_server.py ← existing, unchanged
    └── evacuation_chat.py              ← existing production chat, unchanged
```
