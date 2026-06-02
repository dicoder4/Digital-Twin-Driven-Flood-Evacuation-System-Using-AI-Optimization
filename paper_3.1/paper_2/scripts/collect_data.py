#!/usr/bin/env python3
"""
collect_data.py
===============
Collects real MCP vs non-MCP comparison data for the research paper.

Changes from v1:
  - Uses gemini-1.5-flash (1500 req/day free) instead of gemini-2.5-flash (20/day)
  - Caches non-MCP context token count — counted ONCE, reused for every question
  - Runs compare_many(..., run_judge=False) — judge is a separate script (run_judge.py)
  - inter_question_delay bumped to 75s; per-call sleep added after token counting
  - Computes new metrics per question:
      * useful_tool_call_rate       (MCP-specific)
      * error_recovery_rate         (MCP-specific)
      * hallucination_rate          (both arms)
      * citation_depth              (MCP arm)
      * context_utilization         (non-MCP arm)
      * actionable_words_per_token  (both arms)

Usage:
    python collect_data.py

Prerequisites:
    - Backend server must have run a simulation (MongoDB state must exist)
    - GEMINI_API_KEY and GROQ_API_KEY environment variables must be set
"""

import sys
import json
import os
import time
import asyncio
import re
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent.parent.parent / "UrbanFloodReact" / "backend"
sys.path.insert(0, str(backend_dir))

import google.generativeai as google_genai
from genai.mcp_evacuation_server import _load_state
from genai.context_builder import build_expert_context
from genai.mcp_evaluator import compare_many, DEFAULT_QUESTIONS

# ── Model config ──────────────────────────────────────────────────────────────
# gemini-1.5-flash: 1500 req/day free vs 20/day on gemini-2.5-flash
GEMINI_MODEL_NAME = "gemini-2.5-flash"

google_genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = google_genai.GenerativeModel(GEMINI_MODEL_NAME)

# Delay between questions (seconds).  75s gives both Gemini and Groq time to
# recover between questions on the free tier.
INTER_QUESTION_DELAY_S = 75.0

# Short pause between individual token-count API calls so we don't burn
# through the per-minute request quota on the counting calls themselves.
TOKEN_COUNT_PAUSE_S = 3.0


# ── Token counting ─────────────────────────────────────────────────────────────

def count_tokens_exact(text: str) -> int:
    """Count exact tokens via Gemini API.  Falls back to char/4 on error."""
    try:
        response = gemini_model.count_tokens(text)
        return response.total_tokens
    except Exception as e:
        print(f"  [WARN] Token counting failed: {e}; falling back to approximation")
        return max(1, round(len(text) / 4))


def tool_calls_to_tokens_exact(tool_results: list) -> int:
    """Sum exact tokens across all tool result previews (single API call)."""
    total_text = "\n".join(tr.get("result_preview", "") for tr in tool_results)
    if not total_text.strip():
        return 0
    return count_tokens_exact(total_text)


# ── New metric helpers ─────────────────────────────────────────────────────────

def _extract_numbers(text: str) -> set:
    """Return all numeric strings found in text."""
    return set(re.findall(r"\b\d[\d,\.]*\b", text))


def _extract_shelter_names(text: str, known_shelters: list) -> set:
    """Return which known shelter names appear in text."""
    text_lower = text.lower()
    return {s for s in known_shelters if s.lower() in text_lower}


def compute_hallucination_rate(response_text: str, context_text: str,
                               tool_results: list | None = None) -> float:
    """
    Rough hallucination rate: fraction of numeric claims in the response
    that cannot be found anywhere in the context or tool results.

    Returns a float in [0.0, 1.0].  Returns 0.0 when response is empty.
    """
    if not response_text.strip():
        return 0.0

    response_numbers = _extract_numbers(response_text)
    if not response_numbers:
        return 0.0

    # Build the full grounding corpus
    grounding = context_text
    if tool_results:
        grounding += "\n" + "\n".join(tr.get("result_preview", "") for tr in tool_results)

    grounding_numbers = _extract_numbers(grounding)
    unverified = response_numbers - grounding_numbers
    return round(len(unverified) / len(response_numbers), 3)


def compute_citation_depth(response_text: str, tool_results: list,
                            known_shelters: list) -> float:
    """
    MCP-specific.  Fraction of shelters cited in the response that actually
    appeared in a successful (non-error) tool result.

    Returns 0.0–1.0.  Returns None when no shelters are cited.
    """
    cited = _extract_shelter_names(response_text, known_shelters)
    if not cited:
        return None

    # Shelters that appeared in successful tool results
    grounded = set()
    for tr in tool_results:
        preview = tr.get("result_preview", "")
        if not preview.startswith("Error"):
            grounded |= _extract_shelter_names(preview, known_shelters)

    return round(len(cited & grounded) / len(cited), 3)


def compute_useful_tool_call_rate(tool_calls: list) -> float:
    """
    Fraction of tool calls that returned a non-error result.
    tool_call_count in the raw data counts only successful calls;
    here we use the full tool_calls list length.
    """
    if not tool_calls:
        return 0.0
    errors = sum(1 for tc in tool_calls
                 if str(tc.get("result_preview", "")).startswith("Error"))
    useful = len(tool_calls) - errors
    return round(useful / len(tool_calls), 3)


def compute_error_recovery_rate(tool_calls: list) -> float:
    """
    When a tool call fails, does the model retry the same tool with different
    (correct) args in a subsequent call?

    Returns fraction of errors that were followed by a successful retry of the
    same tool name.  Returns None when there are no errors.
    """
    if not tool_calls:
        return None

    recoveries = 0
    errors = 0
    for i, tc in enumerate(tool_calls):
        if str(tc.get("result_preview", "")).startswith("Error"):
            errors += 1
            # Check if any later call with the same name succeeded
            same_tool_name = tc.get("name")
            for later in tool_calls[i + 1:]:
                if (later.get("name") == same_tool_name and
                        not str(later.get("result_preview", "")).startswith("Error")):
                    recoveries += 1
                    break

    if errors == 0:
        return None
    return round(recoveries / errors, 3)


def compute_context_utilization(response_text: str, context_text: str,
                                known_shelters: list) -> float:
    """
    Non-MCP specific.  Fraction of shelter names present in the full context
    that were actually cited in the response.

    A low value is the core argument FOR MCP — the model was given everything
    but used only a tiny slice of it.
    """
    context_shelters = _extract_shelter_names(context_text, known_shelters)
    if not context_shelters:
        return 0.0
    cited = _extract_shelter_names(response_text, known_shelters)
    return round(len(cited & context_shelters) / len(context_shelters), 3)


def compute_actionable_words_per_token(response_text: str, total_tokens: int) -> float:
    """
    Information density proxy: response word count / total tokens consumed.
    Higher is better — more useful output per token spent.
    """
    if total_tokens == 0:
        return 0.0
    words = len(response_text.split())
    return round(words / total_tokens, 4)


def extract_known_shelters(enriched: dict) -> list:
    """Pull shelter names from the enriched context dict."""
    shelters = enriched.get("shelters", [])
    if shelters and isinstance(shelters[0], dict):
        return [s.get("name", "") for s in shelters if s.get("name")]
    return [str(s) for s in shelters]


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 80)
    print("  MCP vs Non-MCP Comparison Data Collection  (v2 — quota-safe)")
    print("=" * 80)

    # Step 1: Load simulation state
    print("\n[1/5] Loading simulation state from MongoDB...")
    state = _load_state()
    summary_data = state.get("summary_data")
    evacuation_plan = state.get("evacuation_plan", [])

    if not summary_data:
        print("ERROR: No simulation state found in MongoDB.")
        print("Please run a simulation in the app first, then try again.")
        return

    print(f"  [OK] Loaded: {summary_data.get('simulation_location', 'Unknown')} scenario")
    print(f"       - Success rate: {summary_data.get('success_rate_pct', 'N/A')}%")
    print(f"       - Algorithm: {summary_data.get('algorithm', 'N/A')}")

    # Step 2: Build enriched context ONCE
    print("\n[2/5] Building enriched context...")
    try:
        enriched = await build_expert_context(summary_data, evacuation_plan)
        known_shelters = extract_known_shelters(enriched)
        print(f"  [OK] Context built: {len(enriched.get('shelters', []))} shelters, "
              f"{len(enriched.get('pressure_junctures', []))} pressure junctures")
        print(f"  [OK] Known shelters for metric extraction: {len(known_shelters)}")
    except Exception as e:
        print(f"ERROR building context: {e}")
        return

    # Cache non-MCP context token count — ONE API call, reused for all questions.
    # This avoids N separate count_tokens() requests (one per question) that
    # burned through the per-minute quota in v1.
    print("\n  Caching non-MCP context token count (single API call)...")
    context_str = json.dumps(enriched)          # same serialisation used in compare_many
    cached_context_tokens = count_tokens_exact(context_str)
    print(f"  [OK] Non-MCP context = {cached_context_tokens} tokens (cached)")
    time.sleep(TOKEN_COUNT_PAUSE_S)

    # Step 3: Run comparison WITHOUT judge (judge runs separately in run_judge.py)
    print(f"\n[3/5] Running MCP vs non-MCP comparison (judge disabled)...")
    print(f"  Questions   : {len(DEFAULT_QUESTIONS)}")
    print(f"  Model       : {GEMINI_MODEL_NAME}  (both arms via compare_many)")
    print(f"  Inter-Q delay: {INTER_QUESTION_DELAY_S}s")

    try:
        results = await compare_many(
            DEFAULT_QUESTIONS,
            enriched,
            run_judge=False,                        # ← judge is separate now
            inter_question_delay_s=INTER_QUESTION_DELAY_S,
        )
        print(f"  [OK] Completed {len(results)} comparisons")
    except Exception as e:
        print(f"ERROR during comparison: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 4: Enrich results with token counts + new metrics
    print("\n[4/5] Calculating token counts and extended metrics...")

    for i, result in enumerate(results, 1):
        q_short = result["question"][:55]
        print(f"\n  Q{i}: {q_short}...")

        non_mcp = result["non_mcp"]
        mcp     = result["mcp"]

        # ── Non-MCP tokens ────────────────────────────────────────────
        # Prompt token count is the same cached value for every question
        # (the entire enriched context is the prompt for non-MCP).
        non_mcp["prompt_tokens"]   = cached_context_tokens
        non_mcp_response           = non_mcp.get("response_text", "")
        non_mcp["response_tokens"] = count_tokens_exact(non_mcp_response)
        time.sleep(TOKEN_COUNT_PAUSE_S)
        non_mcp_total              = cached_context_tokens + non_mcp["response_tokens"]

        # ── MCP tokens ────────────────────────────────────────────────
        mcp_prompt_text          = result.get("mcp_prompt", "")
        mcp["prompt_tokens"]     = (count_tokens_exact(mcp_prompt_text)
                                    if mcp_prompt_text
                                    else max(1, round(mcp.get("prompt_chars", 0) / 4)))
        time.sleep(TOKEN_COUNT_PAUSE_S)

        mcp_response             = mcp.get("response_text", "")
        mcp["response_tokens"]   = count_tokens_exact(mcp_response)
        time.sleep(TOKEN_COUNT_PAUSE_S)

        mcp_tool_tokens          = tool_calls_to_tokens_exact(mcp.get("tool_calls", []))
        time.sleep(TOKEN_COUNT_PAUSE_S)
        mcp["tool_result_tokens"]= mcp_tool_tokens
        mcp["total_tokens"]      = mcp["prompt_tokens"] + mcp_tool_tokens + mcp["response_tokens"]

        print(f"    Non-MCP : {non_mcp['prompt_tokens']} prompt + {non_mcp['response_tokens']} response = {non_mcp_total} total")
        print(f"    MCP     : {mcp['prompt_tokens']} prompt + {mcp_tool_tokens} tools + {mcp['response_tokens']} response = {mcp['total_tokens']} total")

        # ── Extended metrics ──────────────────────────────────────────
        tool_calls_list = mcp.get("tool_calls", [])

        # Hallucination rate
        non_mcp["extended_metrics"] = {
            "hallucination_rate": compute_hallucination_rate(
                non_mcp_response, context_str
            ),
            "context_utilization": compute_context_utilization(
                non_mcp_response, context_str, known_shelters
            ),
            "actionable_words_per_token": compute_actionable_words_per_token(
                non_mcp_response, non_mcp_total
            ),
        }

        mcp["extended_metrics"] = {
            "hallucination_rate": compute_hallucination_rate(
                mcp_response, context_str, tool_calls_list
            ),
            "citation_depth": compute_citation_depth(
                mcp_response, tool_calls_list, known_shelters
            ),
            "useful_tool_call_rate": compute_useful_tool_call_rate(tool_calls_list),
            "error_recovery_rate": compute_error_recovery_rate(tool_calls_list),
            "actionable_words_per_token": compute_actionable_words_per_token(
                mcp_response, mcp["total_tokens"]
            ),
            # Raw latency stored for the latency-vs-quality scatter in generate_charts.py
            "latency_s": mcp.get("latency_s", None),
        }

        nm = non_mcp["extended_metrics"]
        mm = mcp["extended_metrics"]
        print(f"    Non-MCP extended → halluc={nm['hallucination_rate']:.2f}  "
              f"ctx_util={nm['context_utilization']:.2f}  "
              f"density={nm['actionable_words_per_token']:.4f}")
        print(f"    MCP extended     → halluc={mm['hallucination_rate']:.2f}  "
              f"useful_calls={mm['useful_tool_call_rate']:.2f}  "
              f"recovery={mm['error_recovery_rate']}  "
              f"cite_depth={mm['citation_depth']}  "
              f"density={mm['actionable_words_per_token']:.4f}")

    # Step 5: Save results
    print("\n[5/5] Saving results...")
    output_dir  = Path(__file__).parent.parent / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "comparison_results.json"

    output_data = {
        "metadata": {
            "location":          summary_data.get("simulation_location"),
            "algorithm":         summary_data.get("algorithm"),
            "success_rate_pct":  summary_data.get("success_rate_pct"),
            "questions_count":   len(results),
            "timestamp":         str(asyncio.get_event_loop().time()),
            "model":             GEMINI_MODEL_NAME,
            "judge_included":    False,         # run run_judge.py separately
            "cached_context_tokens": cached_context_tokens,
        },
        "results": results,
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    print(f"  [OK] Saved: {output_path}")

    # ── Summary table ─────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  RESULTS SUMMARY")
    print("=" * 80)

    print(f"\n{'Question':<45} {'Non-MCP tok':<13} {'MCP tok':<10} {'Useful calls':<14} {'Halluc (MCP)'}")
    print("-" * 90)

    for result in results:
        q        = result["question"][:40]
        nm       = result["non_mcp"]
        m        = result["mcp"]
        nm_total = nm.get("prompt_tokens", 0) + nm.get("response_tokens", 0)
        m_total  = m.get("total_tokens", 0)
        ucr      = m.get("extended_metrics", {}).get("useful_tool_call_rate", "—")
        hall     = m.get("extended_metrics", {}).get("hallucination_rate", "—")
        print(f"{q:<45} {nm_total:<13} {m_total:<10} {ucr!s:<14} {hall}")

    avg_non_mcp = sum(
        r["non_mcp"].get("prompt_tokens", 0) + r["non_mcp"].get("response_tokens", 0)
        for r in results
    ) / len(results)
    avg_mcp = sum(r["mcp"].get("total_tokens", 0) for r in results) / len(results)
    reduction = ((avg_non_mcp - avg_mcp) / avg_non_mcp) * 100 if avg_non_mcp else 0

    print(f"\nAverage Non-MCP tokens : {avg_non_mcp:.0f}")
    print(f"Average MCP tokens     : {avg_mcp:.0f}")
    print(f"Token reduction        : {reduction:.1f}%")
    print(f"\n[OK] Data collection complete.  Run run_judge.py next (preferably tomorrow).")
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
