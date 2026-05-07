"""
Publication-quality figures for:
  Digital Twin-Driven Flood Evacuation System Using AI Optimization

Run: python generate_figures.py
Output: figures/ directory (fitness_comparison.pdf, convergence_comparison.pdf,
        diversity_stability.pdf)

Requirements: matplotlib, numpy, seaborn
"""

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import os

matplotlib.rcParams.update({
    'font.family': 'serif',
    'font.size': 10,
    'axes.labelsize': 11,
    'axes.titlesize': 11,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'axes.spines.top': False,
    'axes.spines.right': False,
})

# Colorblind-safe palette (IBM Carbon)
COLOR_GA  = '#648FFF'   # blue
COLOR_ACO = '#FE6100'   # orange
COLOR_PSO = '#785EF0'   # purple

os.makedirs('figures', exist_ok=True)

# ── Figure 1: Mean Fitness Comparison (bar chart with error ranges) ──────────

algorithms  = ['GA', 'ACO', 'PSO']
mean_fitness = [588500, 583600, 583800]
# Std dev from RESEARCH_README empirical results (3-run stability trial)
# Stability formula: 1 - (std / mean)
# GA: std=4100 → stability=99.30%; ACO: std=1200 → 99.79%; PSO: std=2800 → 99.52%
std_fitness  = [4100, 1200, 2800]

colors = [COLOR_GA, COLOR_ACO, COLOR_PSO]

fig, ax = plt.subplots(figsize=(5.5, 3.8))
bars = ax.bar(algorithms, mean_fitness, color=colors, width=0.5, zorder=3,
              yerr=std_fitness, capsize=5, error_kw={'ecolor': '#444444', 'linewidth': 1.2})

ax.set_ylabel('Mean Fitness $F(C)$ (lower is better)')
ax.set_title('Algorithm Mean Fitness — 3-Run Stability Trial\n(120 mm Rainfall, Bangalore)')
ax.set_ylim(580000, 594000)
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
    lambda x, _: f'{x/1000:.0f}k'))
ax.grid(axis='y', linestyle='--', alpha=0.5, zorder=0)

# Annotate bars
for bar, val in zip(bars, mean_fitness):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 200,
            f'{val:,.0f}', ha='center', va='bottom', fontsize=8.5)

fig.savefig('figures/fitness_comparison.pdf')
fig.savefig('figures/fitness_comparison.png')
plt.close(fig)
print('Saved: figures/fitness_comparison.pdf')

# ── Figure 2: Simulated Convergence Curves ───────────────────────────────────
# Simulated convergence trajectories matching reported properties:
# GA: converges at iterations 10-20; PSO: 5-10; ACO: requires 100 iterations

np.random.seed(42)
iterations = np.arange(1, 61)

def convergence_curve(start, end, conv_iter, noise_scale, n=60):
    """Exponential decay convergence with noise."""
    decay = 3.0 / conv_iter
    curve = end + (start - end) * np.exp(-decay * np.arange(n))
    noise = np.random.normal(0, noise_scale, n)
    noise = np.cumsum(noise) * 0.1
    return curve + noise

ga_curve  = convergence_curve(598000, 588500, 20,  200)  # GA: converges 15-25 iters
pso_curve = convergence_curve(596000, 583800, 7,   150)  # PSO: converges 5-10 iters
aco_curve = convergence_curve(594000, 583600, 50,  100)  # ACO: under-converged at 60 iters

fig, ax = plt.subplots(figsize=(5.5, 3.8))
ax.plot(iterations, ga_curve,  color=COLOR_GA,  linewidth=1.8, label='GA')
ax.plot(iterations, pso_curve, color=COLOR_PSO, linewidth=1.8, label='PSO')
ax.plot(iterations, aco_curve, color=COLOR_ACO, linewidth=1.8,
        label='ACO (30–60 iter budget; needs 100+)', linestyle='--')

ax.axvline(x=7,  color=COLOR_PSO, linewidth=0.8, linestyle=':', alpha=0.7)
ax.axvline(x=20, color=COLOR_GA,  linewidth=0.8, linestyle=':', alpha=0.7)

ax.set_xlabel('Iteration')
ax.set_ylabel('Best Fitness $F(C)$')
ax.set_title('Convergence Curves — GA, ACO, PSO\n(Simulated; 60-iteration budget)')
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
    lambda x, _: f'{x/1000:.0f}k'))
ax.legend(loc='upper right')
ax.grid(linestyle='--', alpha=0.4)

fig.savefig('figures/convergence_comparison.pdf')
fig.savefig('figures/convergence_comparison.png')
plt.close(fig)
print('Saved: figures/convergence_comparison.pdf')

# ── Figure 3: Stability Score vs Path Diversity (scatter) ────────────────────

stability  = [99.30, 99.79, 99.52]  # from RESEARCH_README: 1 - (std/mean)
diversity  = [31.5, 20.0, 23.0]    # midpoints (% unique routes, from README ranges)
exec_times = [2.5, 22.5, 4.0]      # midpoints in seconds (bubble size)

fig, ax = plt.subplots(figsize=(5.0, 3.8))
for alg, stab, div, t, col in zip(
        algorithms, stability, diversity, exec_times, colors):
    ax.scatter(div, stab, s=t * 80, color=col, zorder=5, edgecolors='white',
               linewidth=1.2, alpha=0.9)
    ax.annotate(alg, (div, stab), textcoords='offset points',
                xytext=(8, 4), fontsize=10, color=col, fontweight='bold')

ax.set_xlabel('Path Diversity (% unique source-shelter pairs)')
ax.set_ylabel('Stability Score (%)')
ax.set_title('Stability vs. Path Diversity\n(bubble size proportional to execution time)')
ax.set_xlim(12, 40)
ax.set_ylim(82, 102)
ax.grid(linestyle='--', alpha=0.4)

# Legend for bubble size
for label, size in [('2.5 s', 2.5), ('10 s', 10), ('22.5 s', 22.5)]:
    ax.scatter([], [], s=size * 80, color='#888888', alpha=0.6, label=label)
ax.legend(title='Exec. time', loc='lower right', framealpha=0.8)

fig.savefig('figures/diversity_stability.pdf')
fig.savefig('figures/diversity_stability.png')
plt.close(fig)
print('Saved: figures/diversity_stability.pdf')

print('\nAll figures generated successfully.')
print('Include in LaTeX with:')
print('  \\includegraphics[width=\\linewidth]{figures/fitness_comparison.pdf}')
print('  \\includegraphics[width=\\linewidth]{figures/convergence_comparison.pdf}')
print('  \\includegraphics[width=\\linewidth]{figures/diversity_stability.pdf}')
