"""
expert_panel.py — Streaming expert advice via Gemini 2.5 Flash
──────────────────────────────────────────────────────────────
Primary: Gemini 2.5 Flash (google-generativeai SDK, non-streaming REST).
Fallback: Gemini 2.5 Flash (GEMINI_API_KEY_2) (SSE stream).

PATCH LOG:
  Bug 1 — Removed specific item names from PERSONAS["logistics"] example table.
           LLM was copying "Food Packets", "Water Tanker" etc. from few-shot
           examples into the output even when those items don't exist in the data.
  Bug 2 — _generate_gap_analysis() now only checks flood-relevant categories
           (Flood Rescue, Health Services, Shelters, Transportation).
           Previously checked all 7 categories including NBC/SAR heavy equipment
           which are never stocked at fire stations, causing permanent CRITICAL.
  Bug 3 — format_resources_context() now explicitly labels resource sources
           as "RESOURCE SOURCE LOCATIONS" to prevent LLM using fire station
           addresses as shelter destinations.
           stream_advice() now injects a separate "SHELTER DESTINATIONS" section
           into the prompt, clearly separated from resource sources.
  Bug 6 — _load_hobli_coords() now averages coordinates for duplicate hobli
           names instead of silently overwriting with whichever comes last.
"""

import json
import os
import httpx
import pandas as pd
import math
import re

# ── Resource Loader ───────────────────────────────────────────────────────────

def _normalize_hobli_key(name):
    """Normalize hobli name: lowercase, remove spaces, dots, dashes."""
    if not name: return ""
    return re.sub(r'[^a-z0-9]', '', str(name).lower())

def _haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def _load_hobli_coords(data_dir):
    """
    Load hobli coordinates from both urban and rural JSON files.

    BUG 6 FIX: The original code used a plain dict with hobli_name as key,
    so duplicate hobli names (e.g. "Yashavantapura-1" appears twice in urban JSON)
    silently overwrote each other — the coordinate used depended on JSON order.
    Fix: collect all coordinate pairs per key, then average them.
    """
    # Step 1: collect all (lat, lon) pairs per normalized key
    raw: dict[str, list[tuple]] = {}

    for fname in ["hobli_coordinates_urban.json", "hobli_coordinates_rural.json"]:
        path = os.path.join(data_dir, fname)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                try:
                    data = json.load(f)
                    for entry in data:
                        raw_name = entry.get("hobli_name", "")
                        key = _normalize_hobli_key(raw_name)
                        if key:
                            lat = entry.get("latitude")
                            lon = entry.get("longitude")
                            if lat is not None and lon is not None:
                                raw.setdefault(key, []).append((lat, lon))
                except Exception:
                    pass

    # Step 2: average all pairs per key
    coords: dict[str, tuple] = {}
    for key, pairs in raw.items():
        avg_lat = sum(p[0] for p in pairs) / len(pairs)
        avg_lon = sum(p[1] for p in pairs) / len(pairs)
        coords[key] = (avg_lat, avg_lon)

    return coords

def _find_nearest_hobli_with_resources(target_hobli, available_hoblis, data_dir):
    coords = _load_hobli_coords(data_dir)
    target_key = _normalize_hobli_key(target_hobli)

    if target_key not in coords:
        return None, float('inf')

    target_lat, target_lon = coords[target_key]
    nearest_hobli = None
    min_dist = float('inf')

    for h in available_hoblis:
        h_key = _normalize_hobli_key(h)
        if h_key in coords:
            lat, lon = coords[h_key]
            dist = _haversine(target_lat, target_lon, lat, lon)
            if dist < min_dist:
                min_dist = dist
                nearest_hobli = h

    return nearest_hobli, min_dist

# ── Gap Analysis ──────────────────────────────────────────────────────────────

# BUG 2 FIX: Only check these categories for flood disaster gaps.
# The original code checked ALL 7 categories including "Nuclear Biological And
# Chemical" and heavy SAR equipment, which fire stations never stock.
# This caused the gap score to always be near 100% → permanent CRITICAL label.
FLOOD_RELEVANT_CATEGORIES = {
    "Flood Rescue",
    "Health Services",
    "Shelters",
    "Transportation",
}

def _generate_gap_analysis(available_resources: list) -> str:
    """
    Analyse missing resources against standard definitions.

    Only checks flood-relevant categories so the gap score is meaningful
    rather than always 100% (due to NBC / heavy SAR equipment never being
    stocked at fire stations).
    """
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "..", "data", "resource_definitions.json")

        if not os.path.exists(json_path):
            return ""

        with open(json_path, 'r') as f:
            definitions = json.load(f)

        available_items_text = " ".join(
            str(r.get('item', '')).lower() for r in available_resources
        )

        gaps = []
        for category, subcats in definitions.items():

            # BUG 2 FIX: skip categories that are irrelevant for flood response
            if category not in FLOOD_RELEVANT_CATEGORIES:
                continue

            missing_in_cat = []
            checked_count  = 0

            if not isinstance(subcats, dict):
                continue

            items_to_check = []
            for sub, item_list in subcats.items():
                if isinstance(item_list, list):
                    items_to_check.extend(item_list)

            for item_def in items_to_check:
                item_name = item_def.get('name', 'Unknown')
                keyword   = item_name.lower().split('(')[0].strip()
                if len(keyword) < 3:
                    continue

                if keyword not in available_items_text:
                    missing_in_cat.append(item_name)
                checked_count += 1

            if missing_in_cat:
                limit    = 5
                examples = ", ".join(missing_in_cat[:limit])
                if len(missing_in_cat) > limit:
                    examples += f", and {len(missing_in_cat) - limit} more"

                if len(missing_in_cat) > (checked_count * 0.7):
                    status_label = "Severely Lacking"
                else:
                    status_label = "Partially Stocked"

                gaps.append(
                    f"- **{category}** ({status_label}): Missing → {examples}"
                )

        if gaps:
            return (
                "\n### ⚠️ FLOOD-RELEVANT RESOURCE GAPS (vs Standard Definitions):\n"
                + "\n".join(gaps)
            )
        return ""

    except Exception as e:
        print(f"Gap analysis error: {e}")
        return ""


# ── Resource Context Formatter ────────────────────────────────────────────────

def _build_definition_code_map(data_dir: str) -> dict:
    """
    Load resource_definitions.json and build a code → (category, subcategory) map.
    Used to enrich each inventory item with its official classification.
    """
    json_path = os.path.join(data_dir, "resource_definitions.json")
    code_map = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                defs = json.load(f)
            for cat, subcats in defs.items():
                if isinstance(subcats, dict):
                    for subcat, items in subcats.items():
                        if isinstance(items, list):
                            for item in items:
                                code = str(item.get("code", ""))
                                if code:
                                    code_map[code] = (cat, subcat)
        except Exception:
            pass
    return code_map


# Cache the code map at module level (loaded once per process)
_DEF_CODE_MAP: dict | None = None

def _get_def_code_map() -> dict:
    global _DEF_CODE_MAP
    if _DEF_CODE_MAP is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.abspath(os.path.join(base_dir, "..", "data"))
        _DEF_CODE_MAP = _build_definition_code_map(data_dir)
    return _DEF_CODE_MAP


def format_resources_context(resources: list, location_name: str,
                              persona: str = "all") -> str:
    """
    Format resource list for the LLM prompt.

    BUG 3 FIX: Clearly labelled as SUPPLY ORIGINS, not shelter destinations.

    NEW — Persona filtering:
      persona="logistics" → only Logistics CSV items (water, medical, transport, shelter)
      persona="tactical"  → only Tactical CSV items (SAR tools, boats, rescue gear)
      persona="all"       → everything (used for inventory modal, gap analysis)

    NEW — Definition enrichment:
      Each item is labelled with its official category and subcategory from
      resource_definitions.json (matched by item code), so the LLM understands
      the classification of what it's allocating.
    """
    if not resources or (len(resources) == 1 and resources[0].get("type") == "Info"):
        return (
            f"(No specific resources found in IDRN database for '{location_name}'. "
            f"Assume standard district reserves.)"
        )

    code_map = _get_def_code_map()

    # ── Filter by persona ─────────────────────────────────────────────────────
    valid_resources = [r for r in resources if r.get("item") and r.get("type") != "Info"]

    if persona == "logistics":
        valid_resources = [r for r in valid_resources
                           if "logistic" in str(r.get("category", "")).lower()]
    elif persona == "tactical":
        valid_resources = [r for r in valid_resources
                           if "tactical" in str(r.get("category", "")).lower()]

    # ── Group by definition category (enriched) ───────────────────────────────
    # Order that makes sense for field reading
    CAT_ORDER = [
        "Health Services",
        "Flood Rescue",
        "Shelters",
        "Transportation",
        "Search And Rescue",
        "Tele Communication",
        "Nuclear Biological And Chemical",
        "Unknown",
    ]
    from collections import defaultdict
    by_def_cat: dict[str, list] = defaultdict(list)

    for r in valid_resources:
        code = r.get("item_code", "")
        def_cat, def_subcat = code_map.get(code, ("Unknown", ""))
        r["_def_cat"]    = def_cat
        r["_def_subcat"] = def_subcat
        by_def_cat[def_cat].append(r)

    # ── Format header ─────────────────────────────────────────────────────────
    output = [
        f"### RESOURCE SOURCE LOCATIONS FOR '{location_name.upper()}'",
        "⚠️  NOTE: These are SUPPLY ORIGINS (fire stations, hospitals, depots).",
        "    Do NOT use these addresses as shelter destinations in your report.",
        "    Shelter destinations are in the SHELTER DESTINATIONS section below.",
        "",
    ]

    def _fmt(r: dict) -> str:
        dist_raw = r.get("distance") or r.get("distance_km", "N/A")
        d_val, d_str = 999.0, "N/A"
        try:
            if isinstance(dist_raw, (int, float)):
                d_val = float(dist_raw)
                d_str = f"{d_val:.1f} km"
            else:
                clean_d = str(dist_raw).lower().replace("km", "").strip()
                if clean_d and clean_d != "n/a":
                    d_val = float(clean_d)
                    d_str = f"{d_val:.1f} km"
        except Exception:
            pass

        prox = r.get("proximity")
        if not prox:
            prox = ("IMMEDIATE (<5km)" if d_val < 5
                    else "EXTENDED (5-15km)" if d_val < 15
                    else "DISTANT (>15km)")

        subcat = r.get("_def_subcat", "")
        subcat_str = f" [{subcat}]" if subcat else ""
        dept = str(r.get("source", "Unknown")).split(",")[0].strip()  # dept name only

        return (f"  - [{prox}] {d_str} | "
                f"{r.get('item','Item')}{subcat_str} "
                f"(Qty: {r.get('qty','N/A')}) — {dept}")

    for cat in CAT_ORDER:
        items = by_def_cat.get(cat)
        if not items:
            continue
        output.append(f"**{cat}:**")
        for r in items[:150]:
            output.append(_fmt(r))
        output.append("")

    # Append gap analysis (uses full unfiltered list for accuracy)
    gap_text = _generate_gap_analysis(valid_resources)
    if gap_text:
        output.append(gap_text)

    return "\n".join(output)


def _format_shelters_context(shelters: list) -> str:
    """
    Format shelter list into a clearly labelled destination block for the LLM.

    BUG 3 FIX: This new function produces a "SHELTER DESTINATIONS" section
    that is injected separately from the resource sources section.
    The LLM now has an unambiguous list of where to *send* resources.
    """
    if not shelters:
        return "(No shelter data available — use nearest community buildings as fallback destinations.)"

    lines = [
        "### SHELTER DESTINATIONS (Evacuation Centres)",
        "⚠️  NOTE: These are WHERE resources should be SENT.",
        "    These are NOT resource supply points.",
        "",
    ]

    for s in shelters:
        name    = s.get("name", "Unknown Shelter")
        s_type  = s.get("type", "building")
        occ     = s.get("occupancy", 0)
        cap     = s.get("capacity", 0)
        pct     = s.get("occupancy_pct", 0)
        rem     = s.get("remaining_capacity", max(0, cap - occ))
        status  = s.get("status", "UNKNOWN")
        lat     = s.get("lat", "")
        lon     = s.get("lon", "")

        coord_str = f" [coords: {lat}, {lon}]" if lat and lon else ""
        lines.append(
            f"- [{status}] {name} ({s_type}){coord_str} | "
            f"Occupancy: {occ}/{cap} ({pct:.0f}%) | "
            f"Remaining capacity: {rem}"
        )

    return "\n".join(lines)


# ── Personas ──────────────────────────────────────────────────────────────────

PERSONAS = {
    "logistics": """You are the Logistics Chief. Generate a DETAILED yet SCANNABLE logistics report that any field officer can act on immediately.

═══════════════════════════════════════════
ABSOLUTE RULES — violating any = invalid report:
1. SOURCES ≠ DESTINATIONS. Items in "RESOURCE SOURCE LOCATIONS" (fire stations, hospitals) are where you COLLECT FROM. Items in "SHELTER DESTINATIONS" are where you SEND TO. Never swap them.
2. ONLY allocate items that appear verbatim in "RESOURCE SOURCE LOCATIONS". Never invent items.
3. ALLOCATION TABLE: ONE ROW PER SHELTER. ALL items for that shelter go in one "Resources Allocated" cell. Never one row per item.
4. EMPTY SHELTERS: If a shelter receives no resources (stock exhausted), still include its row. Write "⚠️ Resources exhausted — priority resupply needed" in the Resources column. Never leave it blank.
5. STATUS LOGIC:
   - 🟢 STABLE: P1 items (water, medical, boats) exist in inventory AND cover ≥50% of highest-need shelters.
   - 🟡 STRAINED: P1 items exist but are insufficient for all shelters (common situation).
   - 🔴 CRITICAL: P1 items are completely absent from inventory (stock = 0 before any allocation).
6. SOURCING PRIORITY — for each item, follow this order:
   - STEP 1: Use IMMEDIATE (<5km) sources first — instant deployment, no transport delay.
   - STEP 2: If insufficient in immediate, supplement from EXTENDED (5-15km) sources — short turnaround.
   - STEP 3: If still insufficient after both, use DISTANT (>15km) sources — long haul, plan transport.
   - STEP 4: If the item does not exist in ANY proximity zone, it goes in Section 4b (never in inventory).
   In the allocation table "Nearest Source" column, always show the ACTUAL source used (which zone it came from).
7. SECTION 4a is "SHORTAGE AFTER ALLOCATION" — items that existed somewhere in the inventory (immediate, extended, OR distant) but were fully distributed. Do NOT list distant-sourced items here — they were used.
8. SECTION 4b is ONLY for items with zero stock across ALL zones (immediate + extended + distant). These require external procurement.
═══════════════════════════════════════════

REQUIRED STRUCTURE:

# 📦 LOGISTICS REPORT — [Location]
> **Status:** [🟢 STABLE / 🟡 STRAINED / 🔴 CRITICAL] | **Alert:** [Local / Regional / Airlift] | **Shelters:** [N] active | **Total Evacuees:** [N] | **Remaining Capacity:** [N]

---

## 1. SITUATION SUMMARY
3–4 sentences. Cover: (a) overall status and why, (b) which shelters are most critical, (c) biggest single supply constraint, (d) what immediate action is needed.

---

## 2. FULL INVENTORY SNAPSHOT
*Use the exact Definition Category names from the enriched inventory context. Include ALL categories present, not just water/medical.*
*These categories come from the resource definitions: Health Services, Shelters, Transportation, Tele Communication.*
*For each item: sum quantities across all sources.*

| Definition Category | Subcategory | Item | Total Stock | Shortfall / Note |
| :--- | :--- | :--- | :---: | :--- |
| Health Services | Hygiene | Water Tank | 6 | Need 24 more — 24 shelters unserved |
| Health Services | Hygiene | Water Filter | 3 | Need 27 more |
| Health Services | Health Equipment | First Aid Kits | 4 | Need 26 more |
| Health Services | Portable Equipment | Oxygen Cylinders | 76 | Adequate for ~15 shelters |
| Shelters | Sheets | Tarpaulin | 0 | 🚨 CRITICAL — not in inventory |
| Transportation | Light Vehicles | Motor Cycle | [N] | [note] |
| Tele Communication | Wireless System | Walkie Talkie Sets | [N] | [note] |
*(Include every item from the RESOURCE SOURCE LOCATIONS. If stock = 0, still list with "0" and mark 🚨 CRITICAL)*

---

## 3. SHELTER ALLOCATION PLAN
*One row per shelter, sorted by occupancy (highest first).*
*"Why" column = one-line reason for allocation priority.*

| # | Shelter | Status | Pop | Resources Allocated | Why | Nearest Source |
| :--- | :--- | :---: | :---: | :--- | :--- | :--- |
| 1 | [shelter name] | 🔴 CRIT | 488/500 | Water Tank ×1, First Aid ×1, Masks ×10, Life Jackets ×5, Oxygen ×5 | Highest occupancy, near flood zone | Rajajinagara FS (5.3km) |
| 2 | [shelter name] | 🔴 CRIT | 484/500 | Water Tank ×1, Masks ×10, Life Jackets ×5 | Near capacity, no water currently | Yelahanka Hospital (10km) |
| 15 | [shelter name] | 🟡 HIGH | 140/200 | ⚠️ Resources exhausted — priority resupply needed | Stock depleted after critical shelters | Rajajinagara FS (5.3km) |
*(Include ALL [N] shelters — every shelter must have a row)*

---

## 4a. ITEMS ALLOCATED BUT NOW DEPLETED
*These items WERE in inventory and have been fully distributed. More must be procured.*

| Item | Started With | Allocated | Remaining | Urgency |
| :--- | :---: | :---: | :---: | :--- |
| Water Tank | 6 | 6 | 0 | 🚨 Resupply immediately — 24 shelters unserved |
| Life Jackets | 52 | 52 | 0 | 🚨 Resupply — only 6 shelters covered |

---

## 4b. ITEMS NEVER IN INVENTORY (Procurement Required)
*These items do not exist in local supply. Must be requisitioned externally.*

| Item | Daily Need | Source to Request | Method |
| :--- | :--- | :--- | :--- |
| Water Tanker (medium) | 22,875L/day for 7625 people | BWSSB / State Civil Supplies | Regional convoy |
| Tents / Tarpaulin | 50+ units | NDRF / SDRF | Request airlift |

---

## 5. MOBILIZATION NOTES
- **Staging point:** [source name and distance] — reason why chosen
- **Transport available:** [list vehicles from inventory with qty]
- **Recommended dispatch order:** [P1 items first, then P2]
- **Route advisory:** [any flood-related constraints on road access]

---
*Reference: Water 3L/person/day drinking · 15L/person/day hygiene · 3.5m²/person shelter space · 1 toilet per 30 people*
""",

    "tactical": """You are the Tactical Commander. Write a FIELD OPERATIONS report for commanders on the ground.
This is NOT a supply list — that is the Logistics report's job.
Your job: WHERE are the threats, WHO is going there, WHAT are they doing, in what ORDER.

═══════════════════════════════════════════
ABSOLUTE RULES — violating any = invalid report:
1. THREAT ZONES: Use human-readable location names (shelter name, road name, neighbourhood). NEVER use raw database node IDs like "Node 308072421". If you only have a node ID, describe it as the nearest shelter's access road (e.g. "Access road to Fire Station, northwest approach").
2. SOURCES ≠ DESTINATIONS — fire station addresses are supply origins, not shelter destinations.
3. ASSET SOURCING PRIORITY — for each asset deployed in Mission Orders:
   - Use IMMEDIATE (<5km) assets first — ready now, no transport needed.
   - If not available in immediate range, draw from EXTENDED (5-15km) — 15–30 min turnaround.
   - If still insufficient, draw from DISTANT (>15km) — plan convoy/transport, show longer ETA.
   - If an asset does not exist in ANY zone, it goes in Section 5 (Unmet Needs — Escalate Now).
   Always show the correct ETA based on which zone the asset is drawn from.
4. MISSION TABLE: one row per MISSION (a specific task at a specific location). Max 10 missions. Each mission must have a concrete, measurable objective (e.g. "Evacuate 140 persons from Nammura School" not "conduct assessment").
5. SECTOR COMMAND: 3–4 sectors only. "Shelters Covered" cell: list max 3 shelter names then "+ N others". Never list all 10 shelters in one cell.
6. ESCALATION TABLE: de-duplicate — each unmet need appears exactly once. Only list items with zero stock in ALL proximity zones.
7. ASSET SUMMARY: totals only. Do not list every item — that is the Logistics report.
8. Use short, active-voice sentences. No passive voice. No bureaucratic filler.
═══════════════════════════════════════════

REQUIRED STRUCTURE:

# ⚔️ TACTICAL OPS PLAN — [Location]
> **Threat Level:** [🔴 HIGH / 🟡 MEDIUM / 🟢 LOW] | **Active Rescue Zones:** [N] | **Rescue Assets Ready:** [N boats] + [N life jackets] + [N medical personnel] | **SAR Teams:** [N]

---

## 📖 HOW TO READ THIS REPORT
- **Zone (Z-01, Z-02…):** A specific geographic area with an active threat — e.g. a flooded road, overcrowded shelter, or debris blockage. Each zone is assessed and addressed by one or more missions.
- **Mission (M-01, M-02…):** A numbered field order sent to a specific team. Each mission has one location, one objective, and assigned assets. Teams execute missions in priority order (P0 = immediate, P1 = urgent, P2 = low).
- **Sector (Alpha, Bravo…):** A geographic command cluster grouping multiple shelters under one lead team. Sectors enable command-and-control when missions are complete — each lead team owns all shelters in their sector.

---

## 1. THREAT ASSESSMENT

**Summary:** 2 sentences on the overall field situation — what type of flooding, where are people stranded, what are the access barriers.

| Zone | Where (plain English — NO node IDs) | Threat | Severity | People at Risk | Status |
| :--- | :--- | :--- | :---: | :---: | :--- |
| Z-01 | [e.g. Northwest approach to Nammura School, flooded road] | Deep water / stranded residents | 🔴 P0 | [N] | 🚨 Active |
| Z-02 | [e.g. Main road to Community Centre, debris blockage] | Debris / road block | 🟡 P1 | 0 (route only) | 🔧 Clearance needed |
*(Derive zones from route_details distances and shelter types — group nearby origin nodes into one zone)*

---

## 2. TACTICAL ASSET INVENTORY
*Use the exact Definition Category names from the enriched inventory. Include ALL tactical categories: Flood Rescue, Search And Rescue, Nuclear Biological And Chemical.*
*Sum quantities across all sources. List ALL items, not just boats and jackets.*

| Definition Category | Subcategory | Item | Total | Nearest Source | ETA |
| :--- | :--- | :--- | :---: | :--- | :--- |
| Flood Rescue | Rescue Boats | Inflatable Boat (12-person) | 6 | Rajajinagara FS (5.3km) | 15 min |
| Flood Rescue | Specialized Flood/Rescue Equipment | Life Jackets | 52 | Rajajinagara FS | 15 min |
| Flood Rescue | Specialized Flood/Rescue Equipment | Lifebuoy | [N] | [source] | [ETA] |
| Search And Rescue | Cutters | Bolt Cutters | [N] | [source] | [ETA] |
| Search And Rescue | Light Equipment | Crow Bar | [N] | [source] | [ETA] |
| Search And Rescue | Lifting Equipment | Jack With 5 Ton Lift | [N] | [source] | [ETA] |
| Nuclear Biological And Chemical | Nbc Specialized Equipment | Gum Boots | [N] | [source] | [ETA] |
*(Include ALL items from the RESOURCE SOURCE LOCATIONS, grouped by their definition category)*

---

## 3. MISSION ORDERS
*Ordered by priority. Each mission = one specific task at one specific location.*

| ID | Priority | Where | What (action verb + outcome) | Assets | Team | ETA |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- |
| M-01 | 🔴 P0 | [Zone Z-01 location, plain English] | Evacuate [N] stranded residents to [shelter name] | 2× Boats, 15× Life Jackets | Rajajinagara FS team | Immediate |
| M-02 | 🔴 P0 | [Access road to highest-occupancy shelter] | Clear debris to restore ambulance access to [shelter] | Crow Bar ×8, Sledge ×4, Bolt Cutters ×4 | YASHWANTHAPURA FS team | Immediate |
| M-03 | 🟡 P1 | [Medical shelter cluster] | Deploy medical team to assess and treat [N] evacuees at [shelter] | 18× MFR, 8× Paramedics, Stretchers ×6 | Yelahanka Hospital team | 25 min |
*(Continue up to M-10 — each mission distinct, measurable, in plain English)*

---

## 4. SECTOR COMMAND
*3–4 geographic sectors. Each sector has one lead team responsible.*

| Sector | Area / Focus | Shelters (max 3 + count) | Lead Team | Key Task | Priority |
| :--- | :--- | :--- | :--- | :--- | :---: |
| Alpha | Northwest — schools cluster | Nammura School, Soundarya School, Triveni School + 5 others | Rajajinagara FS | Flood rescue + water delivery | 🔴 HIGH |
| Bravo | Central — mixed use | Community Centre, Kendriya Vidyalaya + 3 others | THANISANDRA FS | Debris clearance + logistics | 🟡 MED |
| Charlie | Medical corridor | Ragavendra Hospital, NELAMAHESHWARI Hospital + 12 others | Yelahanka Hospital | Medical triage + oxygen delivery | 🟡 MED |
| Delta | South — low occupancy | Nurture International, Fathima Hospital + 1 other | Secretariat FS | Preparation for incoming evacuees | 🟢 LOW |

---

## 5. UNMET NEEDS — ESCALATE NOW
*Each item listed exactly once. Sorted by urgency.*

| # | What is Needed | Why Critical | Request From | Method |
| :--- | :--- | :--- | :--- | :--- |
| 1 | [specific item] | [specific consequence if not supplied] | NDRF / SDRF / State | Radio / Written requisition |
""",

    "civic": """You are the Public Information Officer. You only COMMUNICATE — you do NOT order supplies or solve logistics.

MANDATORY:
- Use exact numbers from 'simulation' and 'shelter_overview'. Do NOT invent figures.
- Tone: Authoritative, calm, urgent.
- Output MUST strictly embed detailed fields for use in Notification APIs (e.g., coordinates, AI routing).

OUTPUT:
**OFFICIAL SITUATION REPORT (Report Level)**
Affected Zone: [Location]
Evacuation Status: [N] citizens moved to safety.
Remaining Risk: [N] citizens pending evacuation.
Shelter Status: [N] Relief Centres active ([N] at full capacity).
Resource Mobilisation: Logistics and Tactical teams deployed.
Coordinates & Routing: [Lat, Lon] via [Algorithm]

📋 Field Reference Card
💧 Water: 3 L/person/day drinking | 20 L/person/day hygiene.
🏥 Medical: Mass casualty triaging setup.
🍔 Food & Nutrition: [Note standards].
""",
    "sos_expert": """You are the Mass SOS Emergency Broadcaster.
MANDATORY:
- This is a PUBLIC WARNING sent to citizens via SMS/Email.
- Output MUST be bilingual: Kannada and English.
- Keep it extremely short, actionable, and clear.
- Use exact shelter names from the data provided.

OUTPUT FORMAT:
🚨 ತುರ್ತು ಪ್ರವಾಹ ಎಚ್ಚರಿಕೆ / EMERGENCY FLOOD ALERT 🚨
[Location] ದಲ್ಲಿ ಭಾರಿ ಪ್ರವಾಹ ವರದಿಯಾಗಿದೆ. (Heavy flooding reported in [Location].)

✅ ಸುರಕ್ಷಿತ ಸ್ಥಳಗಳು (SAFE ZONES):
[Names of 3 safe shelters with capacity]

❌ ತಪ್ಪಿಸಿ (AVOID):
[Names of full/danger shelters]

🚶‍♂️ ನಿಯಮ (PROTOCOL): 
Civic AI [Algorithm] ವ್ಯವಸ್ಥೆಯು ಒದಗಿಸಿದ ಮಾರ್ಗಗಳ ಮೂಲಕ ಮಾತ್ರ ತೆರಳಿ. (Proceed strictly via optimal routes provided by the Civic AI [Algorithm] System.)

📞 ಸಹಾಯವಾಣಿ (HELPLINE): 112 / 1070. ಯಾರು ಭಯಪಡಬೇಡಿ. (Do not panic.)
""",
    "algo_analyst": """You are a senior AI Algorithm Performance Analyst specialising in metaheuristic optimisation for disaster evacuation.

You are given the results of a 3-run stability test for GA, ACO, and PSO on a real flood evacuation scenario. Each run uses ±5% Gaussian noise on the distance matrix to simulate real-world flood depth uncertainty, forcing algorithms to explore different solution regions.

═══════════════════════════════════════════
ALGORITHM BACKGROUND (use to INTERPRET results, not invent data):

**GA (Genetic Algorithm):**
- Uses crossover (two-point) + mutation (nearest-3 shelter swap) + elitism.
- Population seeded 80% from a greedy nearest-shelter heuristic, 20% random.
- Capacity repair ensures every chromosome is feasible.
- Strengths: robust exploration via crossover, good diversity, handles constraints natively.
- Weakness: crossover can disrupt good sub-routes; may need many generations to recover.

**ACO (Ant Colony Optimisation):**
- Ants construct solutions probabilistically using pheromone × distance heuristic.
- Pheromone evaporation (ρ=0.1) and reinforcement guide convergence.
- Seeded with greedy solution as initial best (warm start).
- Strengths: excels at graph-based routing problems; pheromone accumulation finds shortest paths.
- Weakness: needs MORE iterations (100+) than GA/PSO to build meaningful pheromone trails. With only 30-60 iterations, ACO may not explore beyond its greedy seed — so if convergence_speed=1, it likely means ACO's pheromone matrix didn't have time to differentiate from the greedy.

**PSO (Particle Swarm Optimisation):**
- Uses discrete adaptation with sigmoid-based velocity updates.
- Particles swarm toward personal best (pbest) and global best (gbest).
- Strengths: fastest convergence due to direct attraction toward gbest; efficient for continuous optimisation.
- Weakness: designed for continuous spaces, so discrete shelter assignment is a compromise. Can plateau early if the swarm collapses around gbest.

**Shared Infrastructure:**
- All three use the SAME fitness function: flood-weighted distance + 0.5×travel_time + quadratic capacity overflow penalty + terrain/elevation penalty.
- Fitness values in the millions are normal — they represent cumulative weighted meters × population across all evacuation routes.
- All three start from the same greedy chromosome (nearest-shelter with capacity enforcement).

═══════════════════════════════════════════
METRIC INTERPRETATION GUIDE:

- **mean_fitness (↓ lower = better):** Average best fitness across 5 runs. Differences of 1-2% are significant — they represent thousands of people walking shorter/longer distances.
- **std_dev:** Variance across 5 runs. Higher = less predictable. For real-time disaster response, low std_dev is critical (you can't afford a bad run).
- **stability_score (↑ higher = better):** 1 - (std_dev / mean). Closer to 1.0 = more consistent. BUT: stability = 1.000 exactly means the algorithm returned identical results every run — this suggests it's stuck on the greedy seed, NOT that it's "perfectly stable". Mention this distinction.
- **convergence_speed (↓ lower = faster):** Iteration where 95% of improvement was achieved. Value of 1 means "no improvement beyond initial seed" — the algorithm converged immediately on the greedy solution. This is NOT good — it means the algorithm failed to explore.
- **path_diversity (↑ higher = better):** Fraction of unique origin→shelter assignments. Higher = more spread across shelters (reduces road congestion). Lower = most people funnelled to same few shelters.

═══════════════════════════════════════════
RULES – STRICT:
1. Base your conclusion ONLY on the metrics provided. Do NOT invent data.
2. Use the algorithmic background above to EXPLAIN why an algorithm behaves the way it does (e.g. "ACO's convergence_speed=1 is expected because pheromone matrices need 100+ iterations to diverge from the greedy seed").
3. If convergence_speed=1 for all algorithms, explicitly note that the scenario may be too simple (greedy solution is near-optimal) and recommend increasing iterations or capacity stress.
4. Provide a final ranking (1st, 2nd, 3rd) with clear justification.
5. Include an "Operational Recommendations" section with actionable suggestions.
6. Output MUST be valid Markdown with the following structure:

# 🔬 Algorithm Performance Analysis — [Location]

## 📊 Quantitative Summary
| Algorithm | Mean Fitness ↓ | Std Dev | Stability ↑ | Convergence (iter) ↓ | Diversity ↑ |
|----------|---------------|---------|-------------|----------------------|-------------|
| GA       | ...           | ...     | ...         | ...                  | ...         |
| ACO      | ...           | ...     | ...         | ...                  | ...         |
| PSO      | ...           | ...     | ...         | ...                  | ...         |

## 🧠 Interpretation
Explain each metric row:
- **Mean Fitness:** Which algorithm found the best routes? What does the % difference translate to in real-world terms?
- **Stability:** Which is most reliable? Is any algorithm's "perfect stability" actually greedy-lock?
- **Convergence:** Did any algorithm actually improve beyond the greedy? If convergence=1, why?
- **Diversity:** Which algorithm spreads evacuees most evenly across shelters?

## 🏆 Final Ranking
1. **🥇 [Algo]** – [2-3 sentence justification using metrics + algorithmic theory]
2. **🥈 [Algo]** – [why second]
3. **🥉 [Algo]** – [why third]

## 📋 Operational Recommendations
- **For this scenario:** Which algorithm should the DRA deploy and why?
- **For higher-stress scenarios (more population/fewer shelters):** Which algorithm would likely perform better?
- **To improve analysis quality:** Recommend specific parameter changes (e.g. "Increase ACO iterations to 100+ to allow pheromone differentiation" or "Add more population to stress-test capacity constraints")

## ⚠️ Caveats & Limitations
- Note if the scenario is low-stress (greedy near-optimal)
- Note if iterations are insufficient for ACO's pheromone mechanism
- Note that ±5% noise simulates uncertainty but doesn't change the fundamental graph topology

Do NOT discuss resource allocation, shelter occupancy, or logistics. Focus purely on algorithmic performance.
""",

    "scenario_analyst": """You are a senior AI Algorithm Performance Analyst specialising in disaster evacuation under varying flood intensities.

You are given the results of algorithmic performance (GA, ACO, PSO) across different flood intensity scenarios (e.g., Low, Medium, High).

═══════════════════════════════════════════
RULES – STRICT:
1. Base your conclusion ONLY on the metrics provided. Do NOT invent data.
2. Compare the algorithms across the scenarios. How does increasing flood intensity affect their routing success, execution times, and fitness?
3. Provide a clear conclusion on which algorithm is most robust under high-stress conditions.
4. Output MUST be valid Markdown with the following structure:

# 🌊 Scenario Performance Analysis

## 📊 Cross-Scenario Quantitative Summary
*(Create a concise table comparing key metrics across the scenarios for the algorithms)*

## 🧠 Algorithmic Robustness
Explain how each algorithm handles increasing flood intensity:
- **GA:** ...
- **ACO:** ...
- **PSO:** ...

## 🏆 Final Verdict
Which algorithm would you recommend for unpredictable, high-intensity flood events and why?

## 📋 Operational Recommendations
Actionable suggestions for the emergency response team based on these scenario results.

Do NOT discuss specific resource allocation or logistics. Focus purely on algorithmic robustness across varying flood conditions.
""",
}


# ── Catalog & Guidelines Loaders ──────────────────────────────────────────────

def get_resource_definitions_summary() -> str:
    """Load valid resource categories for prompt validation."""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "..", "data", "resource_definitions.json")
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                data = json.load(f)

            summary = ["### VALID RESOURCE CATALOG (Reference):"]
            for broad_cat, subcats in data.items():
                items_str = []
                for sub, items in subcats.items():
                    if isinstance(items, list):
                        names = [i.get('name') for i in items if isinstance(i, dict)]
                        items_str.extend(names[:5])
                if items_str:
                    summary.append(f"- **{broad_cat}**: {', '.join(items_str)}...")

            return "\n".join(summary)
    except Exception:
        return ""


def get_resource_guidelines() -> str:
    """
    Load official relief standards for use in the AI prompt.
    Returns a SHORT block the AI uses to validate its calculations
    (water per person, shelter area, sanitation ratio).
    This is intentionally minimal — the full reference card is in
    format_guidelines_reference_card() below.
    """
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "..", "data", "resource_guidelines.json")
        if os.path.exists(json_path):
            with open(json_path, "r") as f:
                data = json.load(f)
            ls = data.get("logistics_standards", {})
            wr = ls.get("water_requirements", {})
            ss = ls.get("shelter_specs", {})
            san = ls.get("sanitation_hygiene", {})
            alloc = data.get("allocations_heuristic", {})
            return (
                "CALCULATION STANDARDS (use these numbers only):\n"
                f"- Water (drinking): {wr.get('drinking_liters_person_day', 3)} L/person/day\n"
                f"- Water (hygiene):  {wr.get('hygiene_liters_person_day', 20)} L/person/day\n"
                f"- Water (combined): {alloc.get('water_liters_per_person', 23)} L/person/day\n"
                f"- Shelter area:     {ss.get('area_sqm_person', 3.5)} m²/person\n"
                f"- Sanitation:       1 toilet per {alloc.get('people_per_toilet', 30)} people\n"
                f"- Food:             {alloc.get('food_per_person', 1)} packet/person/day\n"
            )
    except Exception as e:
        print(f"Error loading guidelines: {e}")
        return ""


def format_guidelines_reference_card() -> str:
    """
    Format resource_guidelines.json as a human-readable reference card.
    This is included at the END of every report for field officers to consult.
    The LLM is instructed to copy it verbatim — it must NOT use it for calculation
    (calculations use get_resource_guidelines() numbers only).
    """
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base_dir, "..", "data", "resource_guidelines.json")
        if not os.path.exists(json_path):
            return ""
        with open(json_path, "r") as f:
            data = json.load(f)

        ls  = data.get("logistics_standards", {})
        tp  = data.get("tactical_protocols", {})
        wr  = ls.get("water_requirements", {})
        fn  = ls.get("food_nutrition", {})
        ss  = ls.get("shelter_specs", {})
        san = ls.get("sanitation_hygiene", {})
        med = ls.get("medical_supplies", {})
        rsc = tp.get("rescue_operations", {})
        cm  = tp.get("camp_management", {})

        lines = [
            "---",
            "## 📋 Field Reference Card (Karnataka Disaster Relief Standards)",
            "*For field officer reference only. Do not modify these figures.*",
            "",
            "### 💧 Water",
            f"- Drinking: **{wr.get('drinking_liters_person_day', 3)} L/person/day**",
            f"- Hygiene: **{wr.get('hygiene_liters_person_day', 20)} L/person/day**",
            f"- Note: {wr.get('notes', '')}",
            "",
            "### 🍱 Food & Nutrition",
            f"- Components: {', '.join(fn.get('components', []))}",
            f"- Special groups: {fn.get('special_groups', 'ICDS norms apply')}",
            "",
            "### 🏠 Shelter",
            f"- Space: **{ss.get('area_sqm_person', 3.5)} m²/person**",
            f"- Infrastructure required: {', '.join(ss.get('infrastructure', [])[:3])}",
            f"- Site must NOT be: vulnerable to flooding, landslides, or vector breeding grounds",
            "",
            "### 🚽 Sanitation",
            f"- Ratio: **{san.get('toilets_per_person_ratio', '1:30')} people per toilet**",
            f"- Distance: {san.get('distance_rules', '')}",
            f"- Waste: {san.get('waste_management', 'Collect and dispose regularly')}",
            "",
            "### 🏥 Medical",
            f"- Essential kits: {'; '.join(med.get('essential_kits', [])[:2])}",
            f"- Ambulance: {med.get('ambulance_deployment', 'Station sufficient ambulances with staff')}",
            "",
            "### 🚤 Rescue Priority Order",
            f"- Groups: {' → '.join(rsc.get('priority_groups', ['Severely injured', 'Children', 'Women', 'Elderly']))}",
            "",
            "### 🏕️ Camp Security",
        ]
        for rule in cm.get("security_protocols", []):
            lines.append(f"- {rule}")

        lines += [
            "",
            f"*Source: {data.get('source_document', 'Karnataka Disaster Relief Guidelines')}*",
            "---",
        ]
        return "\n".join(lines)

    except Exception as e:
        print(f"Error formatting guidelines reference card: {e}")
        return ""


# ── Main Streaming Function ───────────────────────────────────────────────────

async def stream_advice(persona: str, summary_data: dict):
    """
    Stream expert advice for the given persona.
    Primary: Gemini 2.5 Flash. Fallback: Gemini 2.5 Flash (GEMINI_API_KEY_2).
    """
    location_name = summary_data.get("simulation", {}).get("location", "TARGET_ZONE_UNSPECIFIED")
    if location_name == "Unknown":
        location_name = "TARGET_ZONE_UNSPECIFIED"

    resources = summary_data.get("local_inventory", [])

    # BUG 3 FIX: Build a separate shelter destinations block so the LLM
    # has unambiguous targets distinct from resource source addresses.
    shelters  = summary_data.get("shelters", [])

    # Filter resources by persona: logistics report only gets logistics CSV items,
    # tactical report only gets tactical CSV items. This prevents cross-contamination
    # (e.g. the logistics report seeing SAR tools it shouldn't allocate, or the
    # tactical report seeing medical personnel it shouldn't deploy).
    resources_text = format_resources_context(resources, location_name, persona=persona)
    shelters_text  = _format_shelters_context(shelters)

    guidelines_text   = get_resource_guidelines()          # short numbers for AI calc
    guidelines_card   = format_guidelines_reference_card() # full card for report footer
    catalog_text      = get_resource_definitions_summary()

    context_str  = json.dumps(summary_data, indent=2)
    system_prompt = PERSONAS.get(persona, PERSONAS["logistics"])

    prompt_text = (
        f"Evacuation Summary:\n{context_str}\n\n"
        f"{resources_text}\n\n"
        f"{shelters_text}\n\n"
        f"VALID RESOURCE CATALOG (Reference Only):\n{catalog_text}\n\n"
        f"CALCULATION STANDARDS (use only for computing quantities):\n{guidelines_text}\n\n"
        f"FIELD REFERENCE CARD (append this section VERBATIM at the very end of your report, "
        f"after Section 5. Do not modify any numbers or text. Do not use it for calculations — "
        f"it is purely for field officers to read):\n{guidelines_card}\n\n"
        f"Provide your expert analysis:"
    )
    nl = "\n\n"

    # ── Primary: Gemini key 1 — buffered so mid-generation failures are clean ──
    # Key 1 accumulates all chunks before sending any to the client.
    # If it fails at any point (start OR mid-generation), the buffer is discarded
    # and key 2 takes over — the client never sees partial key 1 output.
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        key1_buf = []
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=system_prompt,
            )
            response = model.generate_content(prompt_text, stream=True)
            for chunk in response:
                try:
                    text = chunk.text
                except (ValueError, AttributeError):
                    text = None
                if text:
                    key1_buf.append(text)
            # Key 1 completed fully — flush buffer to client
            for text in key1_buf:
                yield "data: " + json.dumps({"text": text}) + nl
            return
        except Exception as e:
            # Key 1 failed — discard any partial buffer silently
            e_str = str(e)
            if "429" in e_str or "quota" in e_str.lower():
                err_short = "quota exceeded"
            elif "API_KEY_INVALID" in e_str or "API key not valid" in e_str or "403" in e_str:
                err_short = "API key invalid"
            elif "finish_reason" in e_str:
                err_short = "safety filter"
            elif "blocked" in e_str.lower():
                err_short = "key blocked"
            else:
                err_short = type(e).__name__
            err_text = f"_(⚠ Key 1 {err_short} — using key 2...)_\n\n"
            yield "data: " + json.dumps({"text": err_text}) + nl

    # ── Fallback: Gemini key 2 — streams live ────────────────────────────────
    gemini_key_2 = os.getenv("GEMINI_API_KEY_2")
    if gemini_key_2:
        k2_sent = False
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key_2)
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash",
                system_instruction=system_prompt,
            )
            for chunk in model.generate_content(prompt_text, stream=True):
                try:
                    text = chunk.text
                except (ValueError, AttributeError):
                    text = None
                if text:
                    yield "data: " + json.dumps({"text": text}) + nl
                    k2_sent = True
            return
        except Exception as e2:
            if not k2_sent:
                yield "data: " + json.dumps({
                    "text": f"_(Gemini key 2 failed: {type(e2).__name__})_\n\n"
                }) + nl
        return  # key 2 existed — never fall through to "no provider"

    yield "data: " + json.dumps({
        "text": "_(No Gemini key available. Set GEMINI_API_KEY or GEMINI_API_KEY_2.)_"
    }) + nl

async def stream_algorithm_analysis(metrics: dict, location: str):
    """
    Stream a performance analysis of GA, ACO, PSO based on their metrics.
    Similar to stream_advice but with a different system prompt and context.
    """
    # Build a minimal context that only contains algorithm_analysis
    context = {
        "algorithm_analysis": metrics,
        "simulation": {"location": location, "algorithm": "Multi-Algo Comparison"}
    }
    context_str = json.dumps(context, indent=2)
    system_prompt = PERSONAS["algo_analyst"]
    
    prompt_text = (
        f"Algorithm comparison metrics for {location}:\n{context_str}\n\n"
        f"Provide your analysis following the required format exactly."
    )
    nl = "\n\n"
    
    # ── Primary: Gemini key 1 — buffered ──────────────────────────────────────
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        buf = []
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system_prompt)
            for chunk in model.generate_content(prompt_text, stream=True):
                try:
                    text = chunk.text
                except (ValueError, AttributeError):
                    text = None
                if text:
                    buf.append(text)
            for text in buf:
                yield "data: " + json.dumps({"text": text}) + nl
            return
        except Exception as e:
            yield "data: " + json.dumps({"text": f"_(⚠ Key 1 {type(e).__name__} — using key 2...)_\n\n"}) + nl

    # ── Fallback: Gemini key 2 — streams live ─────────────────────────────────
    gemini_key_2 = os.getenv("GEMINI_API_KEY_2")
    if gemini_key_2:
        k2_sent = False
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key_2)
            model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system_prompt)
            for chunk in model.generate_content(prompt_text, stream=True):
                try:
                    text = chunk.text
                except (ValueError, AttributeError):
                    text = None
                if text:
                    yield "data: " + json.dumps({"text": text}) + nl
                    k2_sent = True
            return
        except Exception as e2:
            if not k2_sent:
                yield "data: " + json.dumps({"text": f"_(Key 2 failed: {type(e2).__name__})_\n\n"}) + nl
        return

    yield "data: " + json.dumps({"text": "_(No Gemini key available. Set GEMINI_API_KEY or GEMINI_API_KEY_2.)_"}) + nl


async def stream_scenario_analysis(metrics: dict, location: str):
    """
    Stream a performance analysis of GA, ACO, PSO based on scenario metrics.
    """
    context = {
        "scenario_analysis": metrics,
        "simulation": {"location": location, "algorithm": "Multi-Scenario Comparison"}
    }
    context_str = json.dumps(context, indent=2)
    system_prompt = PERSONAS["scenario_analyst"]
    
    prompt_text = (
        f"Scenario comparison metrics for {location}:\n{context_str}\n\n"
        f"Provide your analysis following the required format exactly."
    )
    nl = "\n\n"
    
    # ── Primary: Gemini key 1 — buffered ──────────────────────────────────────
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        buf = []
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system_prompt)
            for chunk in model.generate_content(prompt_text, stream=True):
                try:
                    text = chunk.text
                except (ValueError, AttributeError):
                    text = None
                if text:
                    buf.append(text)
            for text in buf:
                yield "data: " + json.dumps({"text": text}) + nl
            return
        except Exception as e:
            yield "data: " + json.dumps({"text": f"_(⚠ Key 1 {type(e).__name__} — using key 2...)_\n\n"}) + nl

    # ── Fallback: Gemini key 2 — streams live ─────────────────────────────────
    gemini_key_2 = os.getenv("GEMINI_API_KEY_2")
    if gemini_key_2:
        k2_sent = False
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key_2)
            model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=system_prompt)
            for chunk in model.generate_content(prompt_text, stream=True):
                try:
                    text = chunk.text
                except (ValueError, AttributeError):
                    text = None
                if text:
                    yield "data: " + json.dumps({"text": text}) + nl
                    k2_sent = True
            return
        except Exception as e2:
            if not k2_sent:
                yield "data: " + json.dumps({"text": f"_(Key 2 failed: {type(e2).__name__})_\n\n"}) + nl
        return

    yield "data: " + json.dumps({"text": "_(No Gemini key available. Set GEMINI_API_KEY or GEMINI_API_KEY_2.)_"}) + nl

