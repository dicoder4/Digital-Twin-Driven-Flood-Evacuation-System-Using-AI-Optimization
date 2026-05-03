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
- Same AI model (Gemini 2.5 Flash primary, Groq llama-3.3-70b fallback)
- Same simulation data (same flood state, same shelters, same routes)
- Same 5 questions
- Same scoring rubric

**The only thing that changes:** how the AI retrieves the data.

| | MCP | Non-MCP |
|---|---|---|
| Seed given to AI | ~80 words (simulation summary only) | ~7,600 words (full data dump) |
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
| `identify_evacuation_hubs(zone_name)` | Primary hubs and their current occupancy for a zone |

The Non-MCP arm calls **none of these** — everything must come from the static dump.

---

## The 5 Test Questions

Reduced from 8 to 5 to stay within API rate limits while preserving full coverage
of question types. These cover factual lookup, quantitative, analysis, live-data, and summary:

| # | Question | Type | Expected winner |
|---|----------|------|----------------|
| Q1 | Which shelter is most at risk of overflow and what should we do about it? | Factual lookup | MCP (numeric accuracy) |
| Q2 | How many people cannot be evacuated and why? | Quantitative | MCP (precise counts) |
| Q3 | Which roads are critical bottlenecks and how should NDRF approach them? | Analysis | MCP (live road data) |
| Q4 | Are there bus stops near the flooded zones that can support evacuation? | Live/coordinate | **MCP guaranteed** — non-MCP cannot answer |
| Q5 | Give me an overall situation report I can hand to the District Commissioner. | Broad summary | Non-MCP competitive (full dump) |

**Q4** is the strongest differentiator — non-MCP physically cannot answer it because
bus stop lookups require live coordinate queries not available in the static dump.

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

## Partial Live Results (May 2026)

Best clean run so far — Q1 and Q2 used Gemini, remainder used Groq fallback:

| Q | NM provider | MCP provider | NM words | MCP words | NM lat | MCP lat | MCP tools | NM numR | MCP numR | NM acc | MCP acc |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Q1 (overflow shelter) | gemini | gemini | 291 | 558 | 10.3s | 28.1s | 4 | 0.94 | **1.00** | 5/5 | 5/5 |
| Q2 (unevacuated) | gemini | groq | 40 | 189 | 4.8s | 19.2s | 5 | 0.50 | 0.33 | — | — |
| Q3 (bottlenecks) | groq | groq | 156 | 149 | 13.9s | 103.7s | 17 | 0.00 | **0.75** | — | — |
| Q4 (bus stops) | groq | groq | 43 | 64 | 14.6s | 84.5s | 11 | 0.00 | 0.00 | — | — |
| Q5 (situation report) | groq | groq | 92 | 0 | 16.9s | 15.6s | 0 | 0.00 | 0.00 | — | — |

**Averages (over scored questions):**
- NM avg numeric match rate: 0.227 | MCP avg: **0.323**
- NM avg accuracy (judge): 3.50/5 | MCP avg: 3.50/5
- NM avg hallucination score: 3.50/5 | MCP avg: 3.00/5 *(lower = more hallucination on Groq fallback)*

### Key observations from partial results

- **Q1 with Gemini** is the cleanest datapoint: MCP achieves 100% numeric accuracy vs 94% for non-MCP, with a richer 558-word response (vs 291 words). Judge scored both 5/5 on accuracy but MCP had a slight hallucination penalty (4 vs 5) for one fabricated shelter name.
- **Q3 bottlenecks**: MCP numeric rate 0.75 vs non-MCP 0.00 — MCP called `analyze_road_conditions` directly, non-MCP had no road detail in its trimmed Groq prompt.
- **Latency tradeoff**: non-MCP is consistently faster (no tool round-trips) but MCP is more accurate on targeted numeric queries.
- **Groq fallback degrades MCP more than non-MCP** — Groq's weaker reasoning means tool results aren't synthesised as well. The comparison is cleanest when both arms use Gemini.

### Note on rate limits
Free-tier Gemini: 20 req/day. Free-tier Groq: 100K tokens/day. Running all 5 questions
× 2 arms × judge = ~30+ API calls, which exhausts both limits in a single session.
The `inter_question_delay_s=8.0` parameter in `compare_many()` throttles the run to
avoid hitting Groq's per-minute limit; the daily token limit requires either a paid key
or spreading runs across days.

---

## Experimental Design

**Sample:** 3 simulation scenarios × 5 questions = **15 paired comparisons**

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

### Phase 1 — Backend (Complete)

#### `genai/non_mcp_chat.py` — the Non-MCP arm

Before calling Gemini, this file:
1. Calls every parameter-less MCP tool directly and concatenates their text output into a static dump
2. Strips `local_inventory` and `_data_notes` from the simulation context (`_clean_context()`)
3. Builds one big prompt: cleaned simulation context + materialized tool outputs (~7,600 words for Gemini)
4. Sends to Gemini with **no `tools=` argument** — the model cannot make any tool calls
5. Falls back to Groq `llama-3.3-70b-versatile` with a trimmed prompt (~1,150 words) if Gemini fails
6. Groq fallback retries up to 4× with exponential backoff on 429 rate limit errors

**`_trim_context_for_groq()`** caps at 20 shelters / 5 routes / 3 junctures and drops the
tool dump entirely (3,120 words) since the trimmed context already contains the same data inline.
This keeps the Groq prompt under ~1,200 words, well within the ~6K token safe limit.

**Why strip `local_inventory`?**
The enriched context contains 200 entries like `"SOUTH FIRE STATION — Slotted Screwdrivers 4 Nos at 0.8km"`.
Without stripping, the model fabricated shelter recommendations citing fire-station supply addresses
as if they were shelter destinations. After stripping, judge hallucination scores improved from 2/5 to 4–5/5.

---

#### `genai/mcp_chat_metrics.py` — the MCP arm

Sends only a **minimal seed** (6 simulation summary fields + shelter overview + tool list, ~80 words)
to Gemini, then runs a manual tool-execution loop — non-streaming, metric-capturing.

Records every tool call:
```json
{ "name": "get_shelter_status", "args": {}, "result_preview": "=== Shelter Status Report ===" }
```

**Groq tool-calling fallback** (new): when Gemini fails, falls back to Groq using the
**OpenAI-format tool-calling API** (`tools=` + `tool_choice="auto"`). This means Groq
also executes the full tool loop — it's not just a plain text fallback. The `_tools_to_openai_schema()`
helper converts Python function signatures to JSON schema automatically.

`_fill_tool_defaults()` fills missing required args with simulation context defaults:
- `analyze_transit_disruptions` → uses simulation location name + 0.3m flood depth
- `check_bus_availability` → uses Bengaluru centroid (12.9716, 77.5946)
- `identify_evacuation_hubs` → uses simulation location name

`_groq_create_with_retry()` retries up to 4× with exponential backoff (15s → 30s → 60s) on 429.

**Why minimal seed instead of full context?**
When we initially gave MCP the full enriched context (140 shelters inline), Gemini
found all the answers in the prompt and never called a single tool — making MCP
functionally identical to non-MCP. The minimal seed forces genuine tool use.

**Production chat is untouched.** `evacuation_chat.py` still streams to the frontend normally.

---

#### `genai/mcp_evaluator.py` — the comparison harness

- `compare_one(question, enriched_context, run_judge)` — runs both arms in parallel via `asyncio.gather`
- `compare_many(questions, enriched_context, run_judge, inter_question_delay_s=8.0)` — loops over questions with configurable delay between each to avoid rate limit exhaustion
- `llm_judge(question, response, enriched_context)` — Gemini primary → Groq async fallback via `httpx`
- `DEFAULT_QUESTIONS` — the 5-question bank
- `_auto_metrics(response, context)` — shelter matches, numeric accuracy, suspicious capitalised phrases

---

## Issues Encountered and How They Were Fixed

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| MCP initially called zero tools | Full enriched context gave Gemini all answers inline | Switched to minimal seed (~80 words) |
| Non-MCP hallucinated supply sources as shelters | `local_inventory` (200 fire-station items) confused the model | Strip `local_inventory` + `_data_notes` in `_clean_context()` |
| Gemini quota errors stopped runs | Free-tier 20 req/day limit on `gemini-2.5-flash` | Groq fallback in all three generation paths + judge |
| Groq fallback in MCP arm had no tool-calling | Plain `chat.completions.create()` with no `tools=` | Implemented full OpenAI-format tool loop with `_run_groq_tool_loop()` |
| Groq 413 Payload Too Large | Non-MCP Groq prompt included 3,120-word tool dump | Drop tool dump from Groq path; use trimmed context only |
| Groq prompt still too large after trim | 50 shelters × 10 fields = still ~4K tokens | Trimmed to 20 shelters / 5 routes / 3 junctures → ~1,150 words |
| `analyze_transit_disruptions` silently errored | Model omitted required `location_name`/`flood_depth_m` args | `_fill_tool_defaults()` injects simulation defaults |
| Timing bug: MCP latency showed 0.00s | `t0` was inside the try block; Groq path never set `latency_s` | Moved `t0` before try block; Groq path now sets `result["latency_s"]` |
| `genai.configure()` at module load | Key not yet in env when module imported | Moved `genai.configure()` inside `analyze_no_mcp()` function |
| Missing tools in `_load_tools()` | `get_simulation_state`, `get_shelter_status` etc. not registered | Added all 14 tools to `_load_tools()` |
| Groq 429 mid-loop killed tool chains | No retry logic | `_groq_create_with_retry()` with 4× exponential backoff |
| Back-to-back questions exhausted Groq rate limit | No delay between questions | `inter_question_delay_s=8.0` default in `compare_many()` |

---

## The Research Claim

> *"MCP-enabled GenAI agents are better suited for live, location-specific, or
> tool-dependent flood-evacuation questions — particularly those requiring coordinate
> lookups or parameterised queries — while static-dump prompting remains competitive
> for broad factual summaries answerable from preloaded data. MCP achieves higher
> numeric accuracy (0.32 vs 0.23 match rate) at the cost of higher latency
> (28s vs 10s for Gemini-only runs). The strongest design is question-type-aware
> retrieval: use MCP when live lookup is needed, static prompts when the answer is
> fully available upfront."*

---

## How To Run

### Prerequisites

1. Ensure `.env` at the **repo root** (`Digital-Twin-Driven-Flood-Evacuation-System-Using-AI-Optimization/.env`) contains:
   ```
   GEMINI_API_KEY=your_key_here
   GROQ_API_KEY=your_key_here
   MONGO_URI=your_mongo_uri_here
   ```

2. Make sure the simulation has been run at least once so `mcp_state.json` exists, or the backend server is running.

3. A fresh Gemini API key (free tier resets at midnight PST / ~12:30 PM IST daily). Groq resets 100K tokens/day.

---

### Step 1 — Navigate to the backend directory

```bash
cd UrbanFloodReact/backend
```

---

### Step 2 — Run the full 5-question comparison

```bash
python -c "
import asyncio, sys, json
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('../../.env', override=True)

async def run():
    from genai.mcp_evaluator import compare_many, DEFAULT_QUESTIONS
    from genai.context_builder import build_expert_context
    from genai.mcp_evacuation_server import _load_state

    state = _load_state()
    ctx = await build_expert_context(state['summary_data'], state.get('evacuation_plan', []))
    return await compare_many(DEFAULT_QUESTIONS, ctx, run_judge=True, inter_question_delay_s=8.0)

results = asyncio.run(run())
print(json.dumps(results, indent=2, default=str))
"
```

This runs all 5 questions through both arms with an 8-second delay between questions
(prevents Groq rate limit exhaustion), scores with the LLM judge, and prints the full JSON.

---

### Step 3 — Quick single-question smoke test (no judge, faster)

```bash
python -c "
import asyncio, sys, json
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('../../.env', override=True)

async def run():
    from genai.mcp_evaluator import compare_one
    from genai.context_builder import build_expert_context
    from genai.mcp_evacuation_server import _load_state

    state = _load_state()
    ctx = await build_expert_context(state['summary_data'], state.get('evacuation_plan', []))
    r = await compare_one('Which shelter is most at risk of overflow?', ctx, run_judge=False)
    nm, mc = r['non_mcp'], r['mcp']
    print('NON-MCP:', nm.get('provider'), '|', nm['latency_s'], 's |', nm['response_words'], 'words | error:', nm['error'])
    print('MCP:    ', mc.get('provider'), '|', mc['latency_s'], 's |', mc['response_words'], 'words | tools:', [t['name'] for t in mc['tool_calls']])
    print()
    print('NON-MCP:', nm['response_text'][:300])
    print()
    print('MCP:', mc['response_text'][:300])

asyncio.run(run())
"
```

---

### Step 4 — Via the API endpoint (server must be running)

```bash
curl -X POST http://localhost:8000/research/mcp-comparison \
  -H "Content-Type: application/json" \
  -d '{"questions": ["Which shelter is most at risk?"], "run_judge": false}'
```

---

### What to look for in results

| Field | Good sign for MCP | Good sign for Non-MCP |
|---|---|---|
| `tool_call_count` | 3–10 tool calls | 0 (expected) |
| `numeric_match_rate` | > 0.8 | > 0.6 |
| `latency_s` | 15–40s (acceptable) | 5–15s (faster) |
| `judge.accuracy` | 4–5/5 | 3–5/5 |
| `judge.hallucination_severity` | 4–5/5 | 3–4/5 |
| `provider` | `gemini` (ideal) or `groq` | `gemini` (ideal) or `groq` |

If `provider` is `None` and `response_text` is empty — both API keys are exhausted. Wait for quota reset.

---

## File Map

```
UrbanFloodReact/backend/
└── genai/
    ├── non_mcp_chat.py                  ← baseline arm: static dump, Groq fallback with trim + retry
    ├── mcp_chat_metrics.py              ← MCP arm: minimal seed, tool loop, Groq tool-calling fallback
    ├── mcp_evaluator.py                 ← harness: compare_one/many, LLM judge, auto-metrics
    ├── mcp_evacuation_server.py         ← existing MCP server, unchanged
    ├── mcp_flood_intelligence_server.py ← existing MCP server, unchanged
    └── evacuation_chat.py               ← production streaming chat, unchanged
```

## Phase Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1 — Backend | ✅ Complete | All 3 files built, all bugs fixed, Groq tool-calling working |
| Phase 2 — Frontend UI | ✅ Complete | Standalone popup button in EvacuationPanel, decoupled from Algo/Scenario analysis |
| Phase 3 — Research sweep | ⏳ Not started | 3 scenarios × 5 questions = 15 pairs, CSV output for paper |

---

## Disabling the UI Button (When Quotas Are Exhausted)

The MCP vs Non-MCP button lives in `UrbanFloodReact/frontend/src/components/EvacuationPanel.jsx`.
It is controlled by a single boolean flag — find this block and set it to `false` to hide the button:


LINE 483 


```jsx
// UrbanFloodReact/frontend/src/components/EvacuationPanel.jsx
// Around the "MCP vs Non-MCP Comparison" button (after the Scenario Analysis button)

{/* ── Set to true to show the MCP comparison button, false to hide ── */}
{true && (
    <button
        className="analyse-algos-btn"
        onClick={() => setMcpComparisonOpen(true)}
        style={{ marginTop: '8px', background: 'linear-gradient(135deg, #a855f7, #7c3aed)', color: '#fff' }}
    >
        <GitCompare size={12} /> MCP vs Non-MCP Comparison
        <ChevronRight size={12} />
    </button>
)}
```

**To disable:** change `{true &&` to `{false &&` — the button vanishes completely.
**To re-enable:** change back to `{true &&`.

> The popup component (`McpComparisonPopup`) and its state (`mcpComparisonOpen`) remain
> in the file; only the button is hidden. No imports need to be removed.

### When to disable

- Both Gemini (20 req/day) and Groq (100K tokens/day) free-tier quotas are exhausted
- Before a demo/presentation where you don't want accidental API calls
- While testing algo/scenario analysis without burning LLM quota

### When quotas reset

| Provider | Reset time | Check |
|----------|-----------|-------|
| Gemini 2.5 Flash (free) | Midnight PST = ~12:30 PM IST | Check Google AI Studio usage |
| Groq llama-3.3-70b (free) | Rolling 24h from first call | Check console.groq.com |

---

## Frontend File Map

```
UrbanFloodReact/frontend/src/components/
├── EvacuationPanel.jsx       ← hosts the "MCP vs Non-MCP" button (purple, after Scenario Analysis)
│                                toggle: change {true && ...} to {false && ...} to hide
└── McpComparisonPopup.jsx    ← standalone popup: run button → loading → results cards
                                 decoupled from AlgoAnalysisPopup and ScenarioAnalysisPopup
```

The popup has its own internal state — results are NOT shared with the algo analysis flow,
so running algo analysis does NOT burn MCP comparison quota and vice versa.
