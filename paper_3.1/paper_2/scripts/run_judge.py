#!/usr/bin/env python3
"""
run_judge.py
============
Second-pass LLM judge for MCP vs non-MCP comparison results.

Run this script ONE DAY AFTER collect_data.py so that daily token quotas
have fully reset.  This script reads the already-saved comparison_results.json,
scores each response pair with the judge model, then writes an updated JSON
(comparison_results_judged.json) that generate_charts.py reads.

Judge model  : llama-3.1-8b-instant on Groq  (lightweight — judge only needs
               to score short response texts, not reason about complex queries)
Inter-call delay: 90 s between judge calls so we stay well inside the
               100 000 TPD Groq free-tier limit.

Usage:
    python run_judge.py

Prerequisites:
    - comparison_results.json must exist in ../data/  (from collect_data.py)
    - GROQ_API_KEY environment variable must be set
"""

import sys
import json
import os
import time
import re
import traceback
from pathlib import Path

from groq import Groq

# ── Config ────────────────────────────────────────────────────────────────────

# Use the lighter 8B model for judging — it scores text, not reasons about
# disaster scenarios, so the quality difference vs 70B is negligible here.
JUDGE_MODEL = "llama-3.1-8b-instant"

# Delay between judge API calls in seconds.
# 90 s ×  10 calls (5 questions × 2 arms) = 15 min total runtime.
# This keeps the session well inside 100 000 TPD even with generous responses.
INTER_JUDGE_DELAY_S = 90.0

# Paths: try multiple common locations so the script works from different CWDs
DATA_DIR     = Path(__file__).parent.parent / "data"
_candidate_data_dirs = [
    Path(__file__).parent.parent / "data",
    Path(__file__).parent.parent.parent / "data",
    Path.cwd() / "data",
    Path.cwd() / "paper_2" / "data",
    Path(__file__).parent / "data",
]
for _d in _candidate_data_dirs:
    if _d.exists():
        DATA_DIR = _d
        break

INPUT_PATH   = DATA_DIR / "comparison_results.json"
OUTPUT_PATH  = DATA_DIR / "comparison_results_judged.json"

# ── Judge prompt ──────────────────────────────────────────────────────────────

JUDGE_SYSTEM = """You are an expert evaluator for AI responses in disaster-management settings.
Score the response on each dimension from 1 (poor) to 5 (excellent).
Return ONLY a valid JSON object with exactly these keys:
  accuracy, specificity, actionability, hallucination_severity, reasoning
No markdown, no backticks, no extra text."""

JUDGE_USER_TEMPLATE = """Question: {question}

Response to evaluate:
{response}

Score each dimension 1-5:
- accuracy: factual correctness and relevance to the question
- specificity: use of concrete numbers, named locations, or shelter names
- actionability: how directly useful is this for an emergency responder
- hallucination_severity: 1=many hallucinations, 5=no hallucinations detected
- reasoning: brief explanation (1-2 sentences) of the scores

Return ONLY the JSON object."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def call_judge(client: Groq, question: str, response_text: str,
               label: str, q_index: int) -> dict | None:
    """
    Call the Groq judge model and return the parsed score dict.
    Returns None on failure so results can still be saved without this arm.
    """
    prompt = JUDGE_USER_TEMPLATE.format(question=question, response=response_text)

    print(f"    Judging {label}...")
    try:
        completion = client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[
                {"role": "system",  "content": JUDGE_SYSTEM},
                {"role": "user",    "content": prompt},
            ],
            temperature=0.0,
            max_tokens=300,
        )
        raw = completion.choices[0].message.content.strip()

        # Strip markdown fences if the model adds them despite instructions
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()

        scores = json.loads(raw)
        print(f"      acc={scores.get('accuracy')}  spec={scores.get('specificity')}  "
              f"act={scores.get('actionability')}  halluc={scores.get('hallucination_severity')}")
        return scores

    except json.JSONDecodeError as e:
        print(f"      [WARN] JSON parse error: {e} — raw: {raw[:120]}")
        return None
    except Exception as e:
        print(f"      [WARN] Judge call failed: {e}")
        return None


def estimate_groq_tokens(text: str) -> int:
    """Rough token estimate for quota tracking (4 chars ≈ 1 token)."""
    return max(1, round(len(text) / 4))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("  MCP vs Non-MCP — Second-Pass LLM Judge  (quota-safe)")
    print(f"  Model: {JUDGE_MODEL} via Groq")
    print("=" * 80)

    # Step 1: Load existing comparison results
    if not INPUT_PATH.exists():
        print(f"\nERROR: {INPUT_PATH} not found.")
        print("Run collect_data.py first, then re-run this script the next day.")
        sys.exit(1)

    with open(INPUT_PATH) as f:
        data = json.load(f)

    results  = data.get("results", [])
    metadata = data.get("metadata", {})

    if not results:
        print("ERROR: No results found in comparison_results.json.")
        sys.exit(1)

    print(f"\n[OK] Loaded {len(results)} question(s) from {INPUT_PATH}")
    print(f"     Location : {metadata.get('location', 'N/A')}")
    print(f"     Model    : {metadata.get('model', 'N/A')}")
    print(f"     Judge was previously run: {metadata.get('judge_included', False)}")

    # Step 2: Init Groq client — allow multiple ways to provide the API key
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_KEY") or os.getenv("GROQAPIKEY")
    api_key_source = "env" if os.getenv("GROQ_API_KEY") else None

    # Look for key files if env var is not set
    if not api_key:
        # Also check the repository UrbanFloodReact/.env used elsewhere in the project
        _repo_env = Path(__file__).parent.parent.parent.parent / "UrbanFloodReact" / ".env"
        _candidate_key_files = [
            DATA_DIR / "groq_api_key.txt",
            Path.home() / ".groq_api_key",
            Path(__file__).parent.parent / ".env",
            _repo_env,
        ]
        for _kf in _candidate_key_files:
            if _kf.exists():
                try:
                    txt = _kf.read_text(encoding="utf-8")
                    # If the file looks like an env file, extract the GROQ_API_KEY line
                    if "GROQ_API_KEY" in txt:
                        for ln in txt.splitlines():
                            if ln.strip().startswith("GROQ_API_KEY"):
                                _, val = ln.split("=", 1)
                                api_key_candidate = val.strip().strip('"').strip("'")
                                if api_key_candidate:
                                    api_key = api_key_candidate
                                    api_key_source = str(_kf)
                                    print(f"[OK] Loaded GROQ API key from: {_kf}")
                                    break
                        if api_key:
                            break
                    else:
                        api_key = txt.strip()
                        if api_key:
                            api_key_source = str(_kf)
                            print(f"[OK] Loaded GROQ API key from: {_kf}")
                            break
                except Exception:
                    # ignore read errors and continue searching
                    pass

    if not api_key:
        print("\nERROR: GROQ API key not found in environment or key files.")
        print("Set the GROQ_API_KEY environment variable or place the key in one of:")
        for _kf in (
            DATA_DIR / "groq_api_key.txt",
            Path.home() / ".groq_api_key",
            Path(__file__).parent.parent / ".env",
            Path(__file__).parent.parent.parent.parent / "UrbanFloodReact" / ".env",
        ):
            print(f"  - {_kf}")
        sys.exit(1)

    # Masked key display for diagnostics (do not print full key)
    def _mask_key(k: str) -> str:
        if not k:
            return "(none)"
        if len(k) <= 8:
            return "*" * len(k)
        return f"{k[:4]}...{k[-4:]}"

    print(f"[OK] Using GROQ API key from: {api_key_source}  (key: {_mask_key(api_key)})")

    try:
        client = Groq(api_key=api_key)
    except Exception as e:
        print(f"\nERROR: Failed to initialise Groq client: {e}")
        traceback.print_exc()
        sys.exit(1)

    print(f"\n[OK] Groq client initialised — model: {JUDGE_MODEL}")
    print(f"     Inter-call delay: {INTER_JUDGE_DELAY_S}s\n")



    # Step 3: Judge each result
    estimated_tokens_used = 0
    TOKEN_BUDGET = 90_000   # stay safely under 100k TPD

    for i, result in enumerate(results, 1):
        question = result["question"]
        print(f"\n── Q{i}/{len(results)}: {question[:65]}...")

        non_mcp     = result.setdefault("non_mcp", {})
        mcp         = result.setdefault("mcp", {})
        non_response = non_mcp.get("response_text", "")
        mcp_response = mcp.get("response_text", "")

        # Estimate token cost for this pair before calling
        est_cost = (
            estimate_groq_tokens(JUDGE_SYSTEM) * 2 +
            estimate_groq_tokens(question) * 2 +
            estimate_groq_tokens(non_response) +
            estimate_groq_tokens(mcp_response) +
            600   # room for the two judge responses
        )

        if estimated_tokens_used + est_cost > TOKEN_BUDGET:
            print(f"  [WARN] Estimated token budget ({TOKEN_BUDGET}) would be exceeded. "
                  f"Stopping at Q{i} to protect quota.  Re-run tomorrow for remaining questions.")
            break

        # Judge non-MCP arm
        if non_response.strip():
            non_mcp["judge"] = call_judge(client, question, non_response, "Non-MCP", i)
        else:
            print("    [SKIP] Non-MCP response is empty")
            non_mcp["judge"] = None

        print(f"    Waiting {INTER_JUDGE_DELAY_S}s before next judge call...")
        time.sleep(INTER_JUDGE_DELAY_S)

        # Judge MCP arm
        if mcp_response.strip():
            mcp["judge"] = call_judge(client, question, mcp_response, "MCP", i)
        else:
            print("    [SKIP] MCP response is empty")
            mcp["judge"] = None

        estimated_tokens_used += est_cost
        print(f"    Estimated session tokens so far: ~{estimated_tokens_used:,}")

        # Delay before next question pair (skip after last)
        if i < len(results):
            print(f"    Waiting {INTER_JUDGE_DELAY_S}s before next question...")
            time.sleep(INTER_JUDGE_DELAY_S)

    # Step 4: Save updated results
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    output_data = dict(data)   # copy metadata as-is
    output_data["metadata"] = {
        **metadata,
        "judge_included": True,
        "judge_model":    JUDGE_MODEL,
    }
    output_data["results"] = results

    with open(OUTPUT_PATH, "w") as f:
        json.dump(output_data, f, indent=2, default=str)

    print(f"\n[OK] Judged results saved to: {OUTPUT_PATH}")

    # Step 5: Print summary
    print("\n" + "=" * 80)
    print("  JUDGE SCORE SUMMARY")
    print("=" * 80)
    print(f"\n{'Q':<4} {'Non-MCP acc/spec/act/halluc':<30} {'MCP acc/spec/act/halluc'}")
    print("-" * 75)

    for i, result in enumerate(results, 1):
        def fmt(arm):
            j = arm.get("judge") or {}
            if not j:
                return "no score"
            return (f"acc={j.get('accuracy','?')} spec={j.get('specificity','?')} "
                    f"act={j.get('actionability','?')} h={j.get('hallucination_severity','?')}")

        print(f"Q{i:<3} {fmt(result['non_mcp']):<30} {fmt(result['mcp'])}")

    print(f"\n[OK] Done.  Run generate_charts.py to produce updated figures.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
