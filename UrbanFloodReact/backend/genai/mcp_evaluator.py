"""
mcp_evaluator.py — A/B comparison harness for "MCP vs non-MCP" research.
─────────────────────────────────────────────────────────────────────────
Runs the same question through both arms (MCP-enabled and non-MCP) and
returns a structured comparison containing:
  - raw responses from both modes
  - auto-measurable metrics (latency, tokens, hallucinations, numeric accuracy)
  - LLM-judge qualitative scores (Gemini in blind-judge mode)

Public API:
    compare_one(question, enriched_context) -> dict
    DEFAULT_QUESTIONS  — the 8-question paper bank
"""

import json
import asyncio
from concurrent.futures import ProcessPoolExecutor, as_completed
import os
import re


DEFAULT_QUESTIONS = [
    "Which shelter is most at risk of overflow and what should we do about it?",
    "How many people cannot be evacuated and why?",
    "Which roads are critical bottlenecks and how should NDRF approach them?",
    "Are there bus stops near the flooded zones that can support evacuation?",
    "Give me an overall situation report I can hand to the District Commissioner.",
]


# ── Auto-measurable metrics ───────────────────────────────────────────────────

def _extract_shelter_names(enriched_context: dict) -> set:
    """Pull every real shelter name out of the simulation context."""
    names = set()
    for s in enriched_context.get("shelters", []):
        n = s.get("name")
        if n:
            names.add(n.strip())
    return names


def _extract_numeric_facts(enriched_context: dict) -> set:
    """Build the set of numbers (as strings) that appear in the actual sim data."""
    facts = set()

    sim = enriched_context.get("simulation", {})
    for k in ("total_evacuated", "total_at_risk_remaining", "total_at_risk_initial",
              "simulation_population", "success_rate_pct"):
        v = sim.get(k)
        if v is not None:
            facts.add(str(int(v)) if isinstance(v, (int, float)) and float(v).is_integer() else str(v))

    for s in enriched_context.get("shelters", []):
        for k in ("occupancy", "capacity", "remaining_capacity", "occupancy_pct"):
            v = s.get(k)
            if v is not None:
                facts.add(str(int(v)) if isinstance(v, (int, float)) and float(v).is_integer() else str(v))

    ro = enriched_context.get("route_overview", {})
    for k in ("total_routes", "total_people_routed", "avg_distance_m", "max_distance_m",
              "min_distance_m", "largest_group_size"):
        v = ro.get(k)
        if v is not None:
            facts.add(str(int(v)) if isinstance(v, (int, float)) and float(v).is_integer() else str(v))

    return facts


def _auto_metrics(response_text: str, enriched_context: dict) -> dict:
    """
    Compute auto-measurable response-quality metrics:
      - shelter_names_cited       : real shelter names found in response
      - shelter_name_matches      : count of real shelter names in response
      - hallucinated_capitalised  : Title-Case noun phrases that don't match any real shelter
                                    (heuristic — will overcount, but catches blatant invention)
      - numeric_claims            : numbers found in response
      - numeric_matches           : numbers that match real sim facts
      - numeric_match_rate        : numeric_matches / numeric_claims (0 if no claims)
    """
    real_shelters = _extract_shelter_names(enriched_context)
    real_numbers  = _extract_numeric_facts(enriched_context)

    # Shelter-name detection: simple substring (case-insensitive)
    text_lower = response_text.lower()
    cited = [n for n in real_shelters if n.lower() in text_lower]

    # Numeric-claim detection: integers and decimals up to 2dp, ignoring tiny tokens
    nums = re.findall(r"\b\d{2,}(?:\.\d+)?\b", response_text)
    nums = [n for n in nums if n not in {"100"} or "100" in real_numbers]
    matches = sum(1 for n in nums if n in real_numbers)

    # Capitalised-noun heuristic for hallucinated entities
    capitalised_phrases = re.findall(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", response_text)
    common_words = {"District Commissioner", "Bus Stop", "First Aid", "Bus Routes",
                    "Life Jackets", "Critical Shelters", "Pressure Junctures",
                    "Flood Rescue", "Search And Rescue", "Bus Route", "Tactical Commander",
                    "Logistics Chief", "Public Information", "Government Of"}
    suspicious = [
        p for p in set(capitalised_phrases)
        if not any(rs.lower() in p.lower() or p.lower() in rs.lower() for rs in real_shelters)
        and p not in common_words
    ]

    return {
        "shelter_names_cited":       cited,
        "shelter_name_match_count":  len(cited),
        "numeric_claims":            len(nums),
        "numeric_matches":           matches,
        "numeric_match_rate":        round(matches / len(nums), 3) if nums else 0.0,
        "suspicious_capitalised":    suspicious[:10],
    }


# ── LLM-judge ─────────────────────────────────────────────────────────────────

JUDGE_PROMPT = """You are a strict evaluator of AI responses for a flood-evacuation
disaster response system. You are given:
  1. The simulation data ("ground truth").
  2. A user question.
  3. An AI response (which produced this is hidden from you).

Score the response on four dimensions, each 1 (very bad) to 5 (excellent):
  - accuracy:       Does it cite correct shelter names, numbers, and facts from the data?
  - specificity:    Is it data-grounded vs generic boilerplate?
  - actionability:  Could a real NDRF/disaster officer act on this immediately?
  - hallucination_severity: 5 = no hallucinations, 1 = severely hallucinated.

Return ONLY a JSON object on a single line, no prose:
{"accuracy": int, "specificity": int, "actionability": int, "hallucination_severity": int, "reason": "<<one sentence>>"}
"""


def _parse_judge_json(raw: str) -> dict | None:
    """Extract and parse the first JSON object from a judge response string."""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def llm_judge(question: str, response_text: str, enriched_context: dict) -> dict:
    """
    Blind LLM-judge with Gemini primary + Groq fallback.

    Uses Gemini 2.5 Flash first. On any error (including 429 quota exhaustion),
    falls back to Groq llama-3.3-70b which has a much higher free-tier limit.
    This means the research harness keeps working even after Gemini's 20-req/day
    free quota is hit.
    """
    _empty = {"accuracy": None, "specificity": None, "actionability": None,
              "hallucination_severity": None, "reason": "judge skipped"}

    if not response_text.strip():
        return _empty

    # Trim context — keep judge prompt small so it runs quickly on both providers
    trimmed_ctx = {
        "simulation":         enriched_context.get("simulation", {}),
        "shelters":           enriched_context.get("shelters", [])[:15],
        "shelter_overview":   enriched_context.get("shelter_overview", {}),
        "route_overview":     enriched_context.get("route_overview", {}),
        "pressure_junctures": enriched_context.get("pressure_junctures", [])[:5],
    }
    judge_user = (
        f"SIMULATION DATA (ground truth):\n{json.dumps(trimmed_ctx, indent=2)}\n\n"
        f"USER QUESTION:\n{question}\n\n"
        f"AI RESPONSE TO EVALUATE:\n{response_text}\n"
    )

    # ── Primary: Gemini 2.5 Flash ──────────────────────────────────────────────
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        try:
            import google.generativeai as genai
            import asyncio
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=JUDGE_PROMPT)
            loop  = asyncio.get_event_loop()
            resp  = await loop.run_in_executor(None, lambda: model.generate_content(judge_user))
            parsed = _parse_judge_json((resp.text or "").strip())
            if parsed:
                parsed["provider"] = "gemini"
                return parsed
        except Exception:
            pass  # fall through to Groq on any Gemini failure (quota, safety, network)

    # ── Fallback: Groq llama-3.3-70b ──────────────────────────────────────────
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        import httpx
        messages = [
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user",   "content": judge_user},
        ]
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}",
                             "Content-Type": "application/json"},
                    json={"model": "llama-3.3-70b-versatile", "messages": messages,
                          "temperature": 0.1},
                    timeout=30.0,
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                parsed  = _parse_judge_json(content.strip())
                if parsed:
                    parsed["provider"] = "groq"
                    return parsed
                return {**_empty, "reason": "groq judge returned non-JSON"}
        except Exception as groq_err:
            return {**_empty, "reason": f"both providers failed — groq: {groq_err}"}

    return {**_empty, "reason": "no API keys available for judge"}


# ── Top-level comparison ──────────────────────────────────────────────────────

async def compare_one(question: str, enriched_context: dict, run_judge: bool = True) -> dict:
    """
    Run both arms, compute auto metrics, optionally invoke the LLM judge.

    Returns:
        {
          "question": str,
          "non_mcp": { ...analyze_no_mcp output..., "auto_metrics": {...}, "judge": {...} },
          "mcp":     { ...analyze_with_mcp output..., "auto_metrics": {...}, "judge": {...} },
        }
    """
    from genai.non_mcp_chat   import analyze_no_mcp
    from genai.mcp_chat_metrics import analyze_with_mcp

    # Run both arms in parallel — they share the simulation context but are independent
    non_mcp_task = analyze_no_mcp(question, enriched_context)
    mcp_task     = analyze_with_mcp(question, enriched_context)
    non_mcp_res, mcp_res = await asyncio.gather(non_mcp_task, mcp_task)

    non_mcp_res["auto_metrics"] = _auto_metrics(non_mcp_res["response_text"], enriched_context)
    mcp_res["auto_metrics"]     = _auto_metrics(mcp_res["response_text"],     enriched_context)

    if run_judge:
        non_mcp_res["judge"] = await llm_judge(question, non_mcp_res["response_text"], enriched_context)
        mcp_res["judge"]     = await llm_judge(question, mcp_res["response_text"],     enriched_context)
    else:
        non_mcp_res["judge"] = None
        mcp_res["judge"]     = None

    return {
        "question": question,
        "non_mcp":  non_mcp_res,
        "mcp":      mcp_res,
    }


async def compare_many(
    questions: list,
    enriched_context: dict,
    run_judge: bool = True,
    inter_question_delay_s: float = 8.0,
) -> list:
    """Runs compare_one over a list of questions sequentially with a delay between
    each to avoid exhausting Groq's per-minute rate limit mid-run."""
    import asyncio
    out = []
    for i, q in enumerate(questions):
        out.append(await compare_one(q, enriched_context, run_judge=run_judge))
        if i < len(questions) - 1:
            await asyncio.sleep(inter_question_delay_s)
    return out
