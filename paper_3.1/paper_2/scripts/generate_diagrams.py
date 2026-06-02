#!/usr/bin/env python3
"""
generate_diagrams.py
====================
Generates publication-quality architecture and flow diagrams for the paper.

Creates:
1. system_architecture.png - Five-layer architecture diagram
2. context_tree.png - Context Tree data flow pipeline
3. mcp_tool_flow.png - MCP tool-calling sequence diagram
4. digital_twin_ui.png - Mock Digital Twin visualization
5. copilot_screenshot.png - Mock AI Copilot interface
"""

import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
import numpy as np
from pathlib import Path

# Output directory
FIGURES_DIR = Path(__file__).parent.parent / "figures"
DPI = 300
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# Professional colors
COLORS = {
    "blue": "#2196F3",
    "orange": "#FF5722",
    "green": "#4CAF50",
    "purple": "#9C27B0",
    "teal": "#009688",
    "grey": "#757575",
    "light_grey": "#EEEEEE",
    "dark_grey": "#212121",
}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "figure.dpi": DPI,
    "savefig.dpi": DPI,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.1,
})

def save_fig(fig, name):
    """Save figure as PNG and PDF."""
    png_path = FIGURES_DIR / f"{name}.png"
    pdf_path = FIGURES_DIR / f"{name}.pdf"
    fig.savefig(png_path, dpi=DPI, format="png")
    fig.savefig(pdf_path, format="pdf")
    plt.close(fig)
    print(f"  [OK] Saved: {png_path}")
    print(f"  [OK] Saved: {pdf_path}")


# ══════════════════════════════════════════════════════════════════════════════
# Diagram 1: Five-Layer System Architecture
# ══════════════════════════════════════════════════════════════════════════════

def generate_system_architecture():
    """Five-layer architecture: Presentation, Application, Simulation, Intelligence, Data."""
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis('off')

    # Title
    ax.text(5, 11.5, 'Five-Layer Digital Twin + MCP Architecture',
            ha='center', fontsize=12, fontweight='bold')

    # Layer definitions
    layers = [
        ("Layer 1: Presentation", "React Frontend\n(30 components, Leaflet, SSE)", 1, COLORS["blue"]),
        ("Layer 2: Application", "FastAPI Backend\n(service.py, 1,599 lines)", 3, COLORS["orange"]),
        ("Layer 3: Simulation", "Digital Twin Engine\n(Manning's eq., HAND model, SRTM)", 5, COLORS["green"]),
        ("Layer 4: Intelligence", "MCP Server Hub + Context Tree\n(6 servers, 28 tools, Context Tree)", 7, COLORS["purple"]),
        ("Layer 5: Data", "MongoDB + External APIs\n(15+ collections, 11 APIs)", 9, COLORS["teal"]),
    ]

    for title, content, y, color in layers:
        # Layer box
        rect = FancyBboxPatch((0.5, y - 0.4), 9, 1.5,
                             boxstyle="round,pad=0.1",
                             edgecolor=color, facecolor=color, alpha=0.15, linewidth=2)
        ax.add_patch(rect)

        # Text
        ax.text(1, y + 0.5, title, fontsize=10, fontweight='bold', color=color)
        ax.text(1, y, content, fontsize=8, color=COLORS["dark_grey"], va='center')

        # Arrow to next layer
        if y < 9:
            arrow = FancyArrowPatch((5, y - 0.5), (5, y - 1.3),
                                  arrowstyle='->', mutation_scale=20,
                                  color=COLORS["grey"], linewidth=1.5)
            ax.add_patch(arrow)

    fig.suptitle('Digital Twin-driven Flood Evacuation with MCP-Based Agentic AI',
                 fontsize=10, y=0.02)
    save_fig(fig, 'system_architecture')


# ══════════════════════════════════════════════════════════════════════════════
# Diagram 2: Context Tree Data Flow Pipeline
# ══════════════════════════════════════════════════════════════════════════════

def generate_context_tree():
    """Three-stage Context Tree pipeline: Raw Sim Data -> Enrichment -> Tool Context."""
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.axis('off')

    ax.text(5, 7.5, 'Context Tree: From Raw Simulation to Tool-Level Selective Context',
            ha='center', fontsize=11, fontweight='bold')

    # Stage 1: Raw Simulation Data
    rect1 = FancyBboxPatch((0.3, 4.5), 2.5, 2,
                          boxstyle="round,pad=0.1",
                          edgecolor=COLORS["blue"], facecolor=COLORS["blue"],
                          alpha=0.15, linewidth=2)
    ax.add_patch(rect1)
    ax.text(1.55, 5.8, 'Stage 1:', fontsize=9, fontweight='bold', ha='center')
    ax.text(1.55, 5.4, 'Raw Simulation', fontsize=8, ha='center')
    ax.text(1.55, 5.0, 'Shelters, routes,\npressure junctures,\nmetro reports',
            fontsize=7, ha='center', va='center')

    # Stage 2: Enrichment
    rect2 = FancyBboxPatch((3.75, 4.5), 2.5, 2,
                          boxstyle="round,pad=0.1",
                          edgecolor=COLORS["orange"], facecolor=COLORS["orange"],
                          alpha=0.15, linewidth=2)
    ax.add_patch(rect2)
    ax.text(5, 5.8, 'Stage 2:', fontsize=9, fontweight='bold', ha='center')
    ax.text(5, 5.4, 'Enrichment', fontsize=8, ha='center')
    ax.text(5, 5.0, 'Categorize by\nseverity, organize\nby spatial proximity',
            fontsize=7, ha='center', va='center')

    # Stage 3: Tool Context
    rect3 = FancyBboxPatch((7.2, 4.5), 2.5, 2,
                          boxstyle="round,pad=0.1",
                          edgecolor=COLORS["green"], facecolor=COLORS["green"],
                          alpha=0.15, linewidth=2)
    ax.add_patch(rect3)
    ax.text(8.45, 5.8, 'Stage 3:', fontsize=9, fontweight='bold', ha='center')
    ax.text(8.45, 5.4, 'Tool Context', fontsize=8, ha='center')
    ax.text(8.45, 5.0, 'MCP servers\nexpose 28 tools\nfor agent queries',
            fontsize=7, ha='center', va='center')

    # Arrows
    arrow1 = FancyArrowPatch((2.8, 5.5), (3.75, 5.5),
                           arrowstyle='->', mutation_scale=20,
                           color=COLORS["grey"], linewidth=2)
    arrow2 = FancyArrowPatch((6.25, 5.5), (7.2, 5.5),
                           arrowstyle='->', mutation_scale=20,
                           color=COLORS["grey"], linewidth=2)
    ax.add_patch(arrow1)
    ax.add_patch(arrow2)

    # Benefits box
    benefit_box = FancyBboxPatch((1, 2), 8, 1.8,
                               boxstyle="round,pad=0.1",
                               edgecolor=COLORS["purple"], facecolor=COLORS["purple"],
                               alpha=0.1, linewidth=1.5)
    ax.add_patch(benefit_box)
    ax.text(5, 3.4, 'Result: Tool-Level Selective Context Retrieval',
           ha='center', fontsize=9, fontweight='bold', color=COLORS["purple"])
    ax.text(5, 2.7, 'Agent calls only relevant tools based on query semantics',
           ha='center', fontsize=8)
    ax.text(5, 2.2, 'Reduces token consumption by 72.9% vs full-context RAG',
           ha='center', fontsize=8, style='italic')

    save_fig(fig, 'context_tree')


# ══════════════════════════════════════════════════════════════════════════════
# Diagram 3: MCP Tool-Calling Sequence
# ══════════════════════════════════════════════════════════════════════════════

def generate_mcp_tool_flow():
    """Sequence diagram: User Query -> Agent -> Tool Calls -> Results -> Response."""
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis('off')

    ax.text(5, 11.5, 'MCP Agent Tool-Calling Flow',
            ha='center', fontsize=11, fontweight='bold')

    # Actors
    actors = [
        (1.5, 'User Query', COLORS["blue"]),
        (3.5, 'Agent\n(LLM)', COLORS["orange"]),
        (5.5, 'MCP Server 1\n(Tools A-D)', COLORS["green"]),
        (7.5, 'MCP Server 2\n(Tools E-H)', COLORS["purple"]),
        (9, 'Response', COLORS["teal"]),
    ]

    y_base = 10
    for x, label, color in actors:
        circle = Circle((x, y_base), 0.35, color=color, alpha=0.3, linewidth=2,
                       edgecolor=color)
        ax.add_patch(circle)
        ax.text(x, y_base - 0.8, label, ha='center', fontsize=8, fontweight='bold')

    # Sequence steps
    steps = [
        (1.5, 3.5, 9, 'User asks question'),
        (3.5, 5.5, 8.5, 'Call Tool A'),
        (5.5, 7.5, 8, 'Get result'),
        (7.5, 3.5, 7.5, 'Call Tool E (parallel)'),
        (5.5, 7.5, 7, 'Get result'),
        (3.5, 9, 6.5, 'Compose results'),
        (9, 1.5, 6, 'Generate response'),
        (1.5, 9, 5.5, 'Return to user'),
    ]

    y = 9.5
    for x1, x2, y_pos, label in steps:
        arrow = FancyArrowPatch((x1, y_pos), (x2, y_pos),
                              arrowstyle='->', mutation_scale=15,
                              color=COLORS["grey"], linewidth=1.5, linestyle='-')
        ax.add_patch(arrow)
        ax.text((x1 + x2) / 2, y_pos + 0.25, label, ha='center', fontsize=7,
               bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                        edgecolor=COLORS["light_grey"], linewidth=0.5))

    # Key insight box
    insight = FancyBboxPatch((0.5, 2.5), 9, 1.5,
                           boxstyle="round,pad=0.1",
                           edgecolor=COLORS["blue"], facecolor=COLORS["light_grey"],
                           linewidth=1.5)
    ax.add_patch(insight)
    ax.text(5, 3.6, 'Key Innovation: Tools Composed Dynamically by Agent',
           ha='center', fontsize=9, fontweight='bold')
    ax.text(5, 3.05, 'Agent autonomously chains tools across multiple MCP servers',
           ha='center', fontsize=8)
    ax.text(5, 2.6, 'No pre-built composite endpoints needed',
           ha='center', fontsize=8, style='italic')

    save_fig(fig, 'mcp_tool_flow')


# ══════════════════════════════════════════════════════════════════════════════
# Diagram 4: Mock Digital Twin UI (Flood Visualization)
# ══════════════════════════════════════════════════════════════════════════════

def generate_digital_twin_ui():
    """Mock flood map visualization with shelters and routes."""
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.set_aspect('equal')

    # Background (map)
    map_bg = patches.Rectangle((0.5, 0.5), 9, 7, linewidth=2,
                              edgecolor=COLORS["grey"], facecolor='#E3F2FD', alpha=0.3)
    ax.add_patch(map_bg)

    ax.text(5, 7.5, 'Digital Twin UI: Real-Time Flood Visualization',
           ha='center', fontsize=11, fontweight='bold')

    # Flood zones (gradient effect)
    flood1 = patches.Circle((2, 4), 1.2, color=COLORS["blue"], alpha=0.3)
    flood2 = patches.Circle((7, 3), 1.5, color=COLORS["blue"], alpha=0.2)
    ax.add_patch(flood1)
    ax.add_patch(flood2)
    ax.text(2, 4, 'Flood\n0.8m', ha='center', va='center', fontsize=7, fontweight='bold')
    ax.text(7, 3, 'Flood\n0.4m', ha='center', va='center', fontsize=7, fontweight='bold')

    # Shelters (green circles)
    shelters = [(1.5, 6), (3, 5.5), (5.5, 6), (8, 5.5), (4, 2.5)]
    for i, (sx, sy) in enumerate(shelters):
        circle = Circle((sx, sy), 0.25, color=COLORS["green"], alpha=0.7,
                       edgecolor=COLORS["green"], linewidth=1.5)
        ax.add_patch(circle)
        ax.text(sx, sy - 0.6, f'S{i+1}', ha='center', fontsize=7, fontweight='bold')

    # Evacuation routes (orange lines)
    routes = [
        ((2, 4), (1.5, 6)),
        ((2, 4), (3, 5.5)),
        ((7, 3), (5.5, 6)),
        ((7, 3), (8, 5.5)),
    ]
    for start, end in routes:
        ax.plot([start[0], end[0]], [start[1], end[1]],
               color=COLORS["orange"], linewidth=2, alpha=0.6, linestyle='--')

    # Legend
    legend_y = 1.2
    ax.plot([0.7, 1], [legend_y + 0.3, legend_y + 0.3], color=COLORS["blue"],
           linewidth=3, alpha=0.4)
    ax.text(1.3, legend_y + 0.3, 'Flood Zone', fontsize=7, va='center')

    circle = Circle((0.85, legend_y - 0.3), 0.12, color=COLORS["green"], alpha=0.7)
    ax.add_patch(circle)
    ax.text(1.3, legend_y - 0.3, 'Shelter', fontsize=7, va='center')

    ax.plot([0.7, 1], [legend_y - 0.9, legend_y - 0.9], color=COLORS["orange"],
           linewidth=2, alpha=0.6, linestyle='--')
    ax.text(1.3, legend_y - 0.9, 'Evacuation Route', fontsize=7, va='center')

    ax.axis('off')
    save_fig(fig, 'digital_twin_ui')


# ══════════════════════════════════════════════════════════════════════════════
# Diagram 5: Mock AI Copilot Interface
# ══════════════════════════════════════════════════════════════════════════════

def generate_copilot_screenshot():
    """Mock multi-turn agent conversation interface."""
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis('off')

    # Title
    ax.text(5, 9.5, 'AI Copilot: Multi-Turn Agentic Conversation',
           ha='center', fontsize=11, fontweight='bold')

    # Chat interface background
    chat_bg = patches.Rectangle((0.3, 0.5), 9.4, 8.5, linewidth=2,
                               edgecolor=COLORS["grey"], facecolor='#FAFAFA', alpha=0.5)
    ax.add_patch(chat_bg)

    # Messages
    messages = [
        ('User', 'Which shelters are at risk of overflow?', 1, COLORS["blue"]),
        ('Agent [Tool: get_simulation_state]', 'Running get_simulation_state()...', 1.8, COLORS["orange"]),
        ('Agent [Tool: get_shelter_status]', 'Running get_shelter_status()...', 2.5, COLORS["orange"]),
        ('Agent', 'Shelters at risk:\n• Hebbal School: 92% capacity\n• Mathikere Hall: 88% capacity', 3.5, COLORS["green"]),
        ('User', 'What are the recommended actions?', 5.5, COLORS["blue"]),
        ('Agent [Tool: analyze_road_conditions]', 'Analyzing bottlenecks...', 6.2, COLORS["orange"]),
        ('Agent', 'Recommendation: Redirect overflow to\nYeshwanthapura Hall (45% available).\nRoute via ring road (operational).', 7.2, COLORS["green"]),
    ]

    y_pos = 8
    for role, text, y_offset, color in messages:
        # Message bubble
        if 'Agent' in role:
            bubble = FancyBboxPatch((0.5, y_pos - y_offset), 8.5, 0.6,
                                  boxstyle="round,pad=0.1",
                                  edgecolor=color, facecolor=color, alpha=0.15, linewidth=1)
        else:
            bubble = FancyBboxPatch((5.5, y_pos - y_offset), 3.5, 0.6,
                                  boxstyle="round,pad=0.1",
                                  edgecolor=color, facecolor=color, alpha=0.15, linewidth=1)
        ax.add_patch(bubble)

        # Role and text
        if 'Agent' in role:
            ax.text(0.7, y_pos - y_offset + 0.45, f'{role}',
                   fontsize=7, fontweight='bold', color=color, va='center')
            ax.text(0.7, y_pos - y_offset + 0.1, text,
                   fontsize=6, color=COLORS["dark_grey"], va='center')
        else:
            ax.text(5.7, y_pos - y_offset + 0.3, text,
                   fontsize=6, color=COLORS["dark_grey"], va='center')

    save_fig(fig, 'copilot_screenshot')


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  Generating Architecture and Flow Diagrams")
    print("=" * 60)

    print("\n[1/5] System Architecture...")
    generate_system_architecture()

    print("\n[2/5] Context Tree Pipeline...")
    generate_context_tree()

    print("\n[3/5] MCP Tool-Calling Sequence...")
    generate_mcp_tool_flow()

    print("\n[4/5] Digital Twin UI Visualization...")
    generate_digital_twin_ui()

    print("\n[5/5] AI Copilot Interface...")
    generate_copilot_screenshot()

    print("\n" + "=" * 60)
    print("  All diagrams generated successfully!")
    print("=" * 60)
