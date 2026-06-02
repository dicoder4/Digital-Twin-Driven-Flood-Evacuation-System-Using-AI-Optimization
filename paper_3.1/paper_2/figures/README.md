# Figures Directory — IEEE Paper

> Digital Twin + Agentic AI (MCP-based) for Flood Evacuation

This directory contains all figures used in the IEEE journal paper.

---

## Auto-Generated Figures (via `scripts/generate_charts.py`)

Run the script to generate these automatically:

```bash
cd paper_2/scripts
python generate_charts.py
```

| # | Filename                          | Description                                        | Size       |
|---|-----------------------------------|----------------------------------------------------|------------|
| 1 | `token_usage_comparison.png/pdf`  | Grouped bar chart: RAG vs MCP token usage          | Full-width |
| 2 | `tool_distribution.png/pdf`       | Horizontal bar chart: tools per MCP server          | Single-col |
| 3 | `capability_radar.png/pdf`        | Radar chart: RAG vs MCP capability comparison       | Single-col |

---

## Manually Created / Captured Figures

These figures must be **created manually** (screenshots, diagrams, or external tools) and placed in this directory with the filenames listed below.

| # | Expected Filename                  | Description                                                      | Suggested Tool      |
|---|------------------------------------|------------------------------------------------------------------|----------------------|
| 4 | `system_architecture.png/pdf`      | Overall system architecture diagram (DT + MCP + AI agents)       | draw.io / Lucidchart |
| 5 | `mcp_architecture.png/pdf`         | MCP server–client architecture with JSON-RPC flow                | draw.io              |
| 6 | `dt_visualization.png`             | Digital Twin 3D flood visualization screenshot                    | App screenshot       |
| 7 | `agent_reasoning_flow.png/pdf`     | ReAct-style agent reasoning + tool-calling flow diagram           | draw.io / TikZ       |
| 8 | `flood_simulation.png`             | HAND-based flood inundation map for study area                    | App screenshot       |
| 9 | `evacuation_routes.png`            | Optimized evacuation routes on the road network                   | App screenshot       |
| 10| `chatbot_interface.png`            | AI copilot / chatbot interface screenshot                         | App screenshot       |
| 11| `study_area_map.png`               | Study area map (Bangalore) with key landmarks                    | QGIS / Google Maps   |
| 12| `mcp_sequence_diagram.png/pdf`     | Sequence diagram: user query → agent → MCP servers → response    | draw.io / Mermaid    |
| 13| `optimization_convergence.png/pdf` | GA/PSO/ACO convergence curves (if applicable)                    | matplotlib           |

---

## Naming Convention

- Use **lowercase with underscores** for all filenames
- Save in both **PNG (300 DPI)** and **PDF** where applicable
- PNG for screenshots, PDF + PNG for vector diagrams and charts

## IEEE Size Guidelines

| Layout        | Width    | Typical `figsize`       |
|---------------|----------|--------------------------|
| Single column | 3.5 in   | `(3.5, 2.8)`            |
| Full width    | 7.0 in   | `(7.0, 3.5)`            |

Font sizes should be **9–10 pt** for readability in two-column format.
