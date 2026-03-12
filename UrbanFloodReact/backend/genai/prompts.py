"""
prompts.py
──────────
Centralised prompt templates for the GenAI MCP pipeline.

All text that is sent to the Ollama model or rendered as structured
chat output lives here — never inline in mcp_pipeline.py or ollama_agent.py.

Functions return plain strings (or dicts for message lists) so they can be
composed, tested and updated independently of the pipeline logic.
"""

from __future__ import annotations


# ── System prompt ─────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    """
    Full system prompt for the SimHelper agent.
    Used by AsyncOllamaAgent as the permanent system message in every chat.
    """
    return (
        "You are SimHelper — the AI flood simulation and evacuation assistant "
        "for the Urban Flood Digital Twin System covering Bengaluru, India.\n\n"

        "## Your Role\n"
        "You assist disaster-response authorities in:\n"
        "- Triggering flood simulations for specific hoblis (sub-districts) in Bengaluru.\n"
        "- Interpreting real-time and historical rainfall data.\n"
        "- Explaining evacuation plans, shelter occupancy, and route strategies.\n"
        "- Providing clear, authoritative guidance suitable for emergency personnel.\n\n"

        "## Bengaluru Hobli System\n"
        "Bengaluru is divided into hoblis under two taluks:\n"
        "- **Bengaluru Urban** (BBMP area): Yelahanka, Jala, Dasarahalli, Byatarayanapura, "
        "Yeshwanthapura, Bangalore North, K.R. Pura, Mahadevapura, Bangalore East, "
        "Bangalore South, Bommanahalli, Begur, Anekal.\n"
        "- **Bengaluru Rural** (peripheral): Sarjapura, Attibele, Kasaba (Anekal), "
        "Varthur, Bidarahalli, Hoskote, Devanahalli, Doddaballapur.\n"
        "Many hoblis have numbered variants (e.g. Sarjapura-1, Sarjapura-2).\n\n"

        "## Strict Rules\n"
        "1. NEVER invent rainfall figures. Always use values sourced from the weather "
        "   server (Open-Meteo) or validated IMD historical records.\n"
        "2. NEVER run a simulation without operator confirmation of the rainfall value.\n"
        "3. When multiple hobli variants exist, use the primary (first) match unless told otherwise.\n"
        "4. Present all data in clear tabular or bullet format for emergency readability.\n"
        "5. Be concise — emergency responders need fast answers.\n\n"

        "## Available Tools\n"
        "- `get_weather(hobli_name, mode, days_back)` — fetches rainfall for a hobli.\n"
        "- `run_simulation(hobli_name, rainfall_mm, steps, algorithm)` — triggers evacuation simulation.\n\n"

        "Always be professional, precise, and safety-focused."
    )


# ── Rainfall mode question ────────────────────────────────────────────────────

def rainfall_mode_question(hobli_display: str, rain_min: float, rain_max: float,
                            rain_mean: float, rain_std: float,
                            matches_note: str = "") -> str:
    """
    Step 1 prompt: ask operator whether to use realtime or historical rainfall.
    """
    return (
        f"## 🌊 Flood Simulation Request — {hobli_display}\n\n"
        f"**Valid rainfall range:** {rain_min}–{rain_max} mm  \n"
        f"**Historical mean:** {rain_mean} mm ± {rain_std} mm"
        f"{matches_note}\n\n"
        f"---\n\n"
        f"### 🌧️ Rainfall Source\n\n"
        f"Before running the simulation, I need a physically valid rainfall value.\n"
        f"How would you like to source it?\n\n"
        f"1. **Real-time** — fetch current precipitation from Open-Meteo right now\n"
        f"2. **Historical** — I'll analyse {hobli_display}'s IMD monsoon records and "
        f"present **3 flood scenarios** for you to choose from\n\n"
        f"_Type **1** or **realtime**, or **2** or **historical** to choose._"
    )


# ── Historical scenario reasoning prompt (sent to Ollama) ─────────────────────

def historical_scenario_reasoning_prompt(
    hobli_display: str,
    district: str,
    record_count: int,
    rain_mean: float,
    rain_std: float,
    rain_min: float,
    rain_max: float,
    scenario_low: float,
    scenario_medium: float,
    scenario_high: float,
) -> str:
    """
    One-shot prompt sent to Ollama to reason over 3 rainfall scenarios for a
    hobli and recommend which is most appropriate for flood evacuation planning.

    The model should present the scenarios in a clear format, explain the
    trade-offs, and ask the operator to pick one.
    """
    return (
        f"You are SimHelper, an emergency flood planning AI for Bengaluru, India.\n\n"
        f"I have computed three historical monsoon rainfall scenarios for "
        f"**{hobli_display}** ({district} district) based on {record_count} "
        f"IMD rainfall records (monsoon season, May–October):\n\n"
        f"| # | Scenario     | Rainfall | Percentile        |\n"
        f"|---|--------------|----------|-------------------|\n"
        f"| 1 | Conservative | {scenario_low:.1f} mm  | ~50th percentile |\n"
        f"| 2 | Moderate     | {scenario_medium:.1f} mm  | ~75th percentile |\n"
        f"| 3 | Severe       | {scenario_high:.1f} mm  | ~90th percentile |\n\n"
        f"Historical stats: mean={rain_mean} mm, std={rain_std} mm, "
        f"valid range=[{rain_min}–{rain_max}] mm.\n\n"
        f"Your task:\n"
        f"1. In 2-3 sentences, explain what each scenario would mean for flood "
        f"   inundation depth and impact on evacuation routes in an urban hobli "
        f"   like {hobli_display}.\n"
        f"2. Give your recommendation on which scenario best stress-tests the "
        f"   evacuation network without being unrealistically extreme.\n"
        f"3. End with: \"**Which scenario would you like to simulate? Type 1, 2, or 3.**\"\n\n"
        f"Be concise and authoritative. Use markdown formatting."
    )


# ── Realtime rainfall table ───────────────────────────────────────────────────

def realtime_rainfall_table(
    hobli_display: str,
    rainfall_mm: float,
    source_note: str,
    condition: str,
    temp_c,
    rain_min: float,
    rain_max: float,
    clamp_note: str = "",
) -> str:
    """Markdown table shown after fetching real-time weather."""
    out = (
        f"### 🌧️ Rainfall Resolved — Real-time\n\n"
        f"| Parameter         | Value |\n"
        f"|-------------------|-------|\n"
        f"| **Rainfall (mm)** | **{rainfall_mm} mm** |\n"
        f"| **Source**        | {source_note} |\n"
        f"| **Condition**     | {condition} |\n"
        f"| **Temperature**   | {temp_c} °C |\n"
        f"| **Valid range**   | {rain_min}–{rain_max} mm |\n"
    )
    if clamp_note:
        out += f"\n> ⚠️ {clamp_note}\n"
    return out


# ── Simulation confirmation prompt ────────────────────────────────────────────

def simulation_confirmation_prompt(
    hobli_display: str,
    rainfall_mm: float,
    source: str,
    scenario_label: str = "",
) -> str:
    """Ask operator to confirm before running the simulation."""
    scenario_line = f"- Scenario: _{scenario_label}_\n" if scenario_label else ""
    return (
        f"\n---\n\n"
        f"🤔 **Ready to run simulation with {rainfall_mm} mm rainfall.**\n\n"
        f"- Hobli: **{hobli_display}**\n"
        f"- Rainfall: **{rainfall_mm} mm**\n"
        f"{scenario_line}"
        f"- Source: _{source}_\n"
        f"- Algorithm: **GA** (Genetic Algorithm)\n\n"
        f"Shall I go ahead? _Type **yes** to confirm, or **no** to cancel._"
    )


# ── Simulation launch message ─────────────────────────────────────────────────

def simulation_launch_message(hobli_display: str, rainfall_mm: float) -> str:
    return (
        f"\n🚀 **Launching flood simulation** for **{hobli_display}** "
        f"with {rainfall_mm} mm rainfall...\n\n"
        f"⏳ _This may take 30–90 seconds while the evacuation algorithm runs._\n\n"
    )


# ── Simulation result narrative prompt (sent to Ollama) ───────────────────────

def sim_result_narrative_prompt(
    hobli_display: str,
    rainfall_mm: float,
    total_population: int,
    at_risk: int,
    evacuated: int,
    still_at_risk: int,
    success_rate: float,
    algorithm: str,
    exec_time: float,
    shelter_count: int,
) -> str:
    """
    One-shot prompt asking Ollama to write a 2-3 sentence narrative summary
    of the simulation results for display below the metrics table.
    """
    return (
        f"You are SimHelper, an AI flood response assistant for Bengaluru.\n\n"
        f"A flood simulation just completed for **{hobli_display}** with "
        f"**{rainfall_mm} mm** of rainfall. Here are the results:\n\n"
        f"- Total population in affected zones: {total_population:,}\n"
        f"- Initially at risk: {at_risk:,}\n"
        f"- Successfully evacuated: {evacuated:,}\n"
        f"- Still at risk after simulation: {still_at_risk:,}\n"
        f"- Evacuation success rate: {success_rate}%\n"
        f"- Algorithm used: {algorithm}\n"
        f"- Computation time: {exec_time}s\n"
        f"- Number of shelters involved: {shelter_count}\n\n"
        f"Write a **2–3 sentence authoritative summary** of what these results mean "
        f"for emergency responders — highlight whether the evacuation was successful, "
        f"any concern about remaining at-risk population, and one immediate action "
        f"recommendation. Use a calm, professional tone. Do NOT repeat the raw numbers "
        f"verbatim — interpret them."
    )


# ── Simulation metrics table ──────────────────────────────────────────────────

def simulation_metrics_table(
    hobli_display: str,
    rainfall_mm: float,
    algorithm: str,
    total_population,
    at_risk_initial,
    total_evacuated,
    at_risk_remaining,
    success_rate,
    exec_time,
) -> str:
    """Markdown metrics table shown after simulation completes."""
    return (
        f"## ✅ Simulation Complete\n\n"
        f"| Metric                    | Value |\n"
        f"|---------------------------|-------|\n"
        f"| **Hobli**                 | {hobli_display} |\n"
        f"| **Rainfall**              | {rainfall_mm} mm |\n"
        f"| **Algorithm**             | {algorithm} |\n"
        f"| **Total Population**      | {total_population:,} |\n"
        f"| **At Risk (initial)**     | {at_risk_initial:,} |\n"
        f"| **Evacuated**             | {total_evacuated:,} |\n"
        f"| **Still At Risk**         | {at_risk_remaining:,} |\n"
        f"| **Success Rate**          | {success_rate}% |\n"
        f"| **Execution Time**        | {exec_time}s |\n"
    )


# ── Shelter occupancy table ───────────────────────────────────────────────────

def shelter_occupancy_table(shelters: list[dict]) -> str:
    """Markdown shelter occupancy table (top 8)."""
    lines = [
        "\n### 🏠 Shelter Occupancy\n\n",
        "| Shelter | Occupancy | Capacity | Fill % |\n",
        "|---------|-----------|----------|---------|\n",
    ]
    for s in shelters[:8]:
        name = str(s.get("name", s.get("id", "N/A")))[:30]
        lines.append(
            f"| {name} "
            f"| {s.get('occupancy', 0):,} "
            f"| {s.get('capacity', 0):,} "
            f"| {s.get('occupancy_pct', 0)}% |\n"
        )
    return "".join(lines)


# ── Route insights prompt (sent to Ollama after simulation) ───────────────────

def route_insights_prompt(
    hobli_display: str,
    rainfall_mm: float,
    algorithm: str,
    total_evacuated: int,
    success_rate: float,
    shelters: list[dict],
    evacuation_plan: list[dict],
) -> str:
    """
    One-shot prompt giving Ollama the shelter-route summary to produce a
    structured 4-section route analysis block.

    Expected sections in Ollama's response:
      ### Overall Assessment
      ### ✅ Viable Routes
      ### ⚠️ Concerns
      ### 🚨 Priority Action
    """
    # Build compact shelter table for the prompt
    shelter_lines = []
    for s in shelters[:8]:
        name       = str(s.get("name", s.get("id", "Shelter")))[:28]
        occ_pct    = s.get("occupancy_pct", 0)
        capacity   = s.get("capacity", 0)
        is_flooded = s.get("is_flooded", False) or s.get("flooded", False)
        safety     = "⚠️ FLOODED" if is_flooded else "✅ safe"
        shelter_lines.append(
            f"- **{name}**: {occ_pct}% full ({capacity} capacity) — {safety}"
        )

    # Build evacuation plan summary (zone → shelter assignments + counts)
    plan_lines = []
    seen: dict[str, int] = {}
    for entry in (evacuation_plan or []):
        shelter_id = str(entry.get("shelter_id") or entry.get("shelter") or "")
        seen[shelter_id] = seen.get(shelter_id, 0) + 1
    for sid, count in list(seen.items())[:8]:
        plan_lines.append(f"- {count} zone(s) → shelter `{sid}`")

    shelter_block = "\n".join(shelter_lines) if shelter_lines else "No shelter data available."
    plan_block    = "\n".join(plan_lines)    if plan_lines    else "No route assignments available."

    return (
        f"You are SimHelper, an emergency flood response AI for Bengaluru.\\n\\n"
        f"A flood simulation for **{hobli_display}** just completed "
        f"({rainfall_mm} mm, {algorithm} algorithm). "
        f"**{total_evacuated:,}** people were evacuated ({success_rate}% success rate).\\n\\n"
        f"## Shelter Status\\n{shelter_block}\\n\\n"
        f"## Route Assignments (zone → shelter)\\n{plan_block}\\n\\n"
        f"Produce a concise **route analysis** with EXACTLY these four sections:\\n\\n"
        f"### Overall Assessment\\n"
        f"(2 sentences: how well did the evacuation network perform?)\\n\\n"
        f"### ✅ Viable Routes\\n"
        f"(bullet per well-utilised shelter/route — name, zone count, capacity note)\\n\\n"
        f"### ⚠️ Concerns\\n"
        f"(any shelter >85% full, flooded shelter, or under-served zones)\\n\\n"
        f"### 🚨 Priority Action\\n"
        f"(single most important operational recommendation for emergency responders)\\n\\n"
        f"Be specific to {hobli_display}. Do NOT invent data not shown above. "
        f"Use markdown formatting. Keep total response under 200 words."
    )

