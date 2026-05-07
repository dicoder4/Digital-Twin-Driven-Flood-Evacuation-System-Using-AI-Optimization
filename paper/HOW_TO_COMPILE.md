# How to Compile the Paper

## Option 1: Overleaf (Recommended — no local install needed)
1. Go to https://www.overleaf.com and create a free account
2. Click "New Project" → "Upload Project"
3. Upload a ZIP of this `paper/` folder
4. Set main file to `main.tex`
5. Compiler: **pdfLaTeX** (or LuaLaTeX)
6. Click Compile — done

## Option 2: Local TeX Live (Windows)
1. Install MiKTeX: https://miktex.org/download
2. Open terminal in this `paper/` directory
3. Run:
   ```
   pdflatex main.tex
   bibtex main
   pdflatex main.tex
   pdflatex main.tex
   ```
4. Open `main.pdf`

## Option 3: VS Code with LaTeX Workshop extension
1. Install the "LaTeX Workshop" VS Code extension
2. Open `main.tex`
3. Ctrl+Alt+B to build

## Generating Figures
Before compiling, generate the figures:
```
cd paper/
python figures/generate_figures.py
```
This creates `figures/fitness_comparison.pdf`, `figures/convergence_comparison.pdf`,
and `figures/diversity_stability.pdf`.

To include them in the paper, add to the relevant section in `main.tex`:
```latex
\begin{figure}[H]
  \centering
  \includegraphics[width=\linewidth]{figures/fitness_comparison.pdf}
  \caption{Algorithm mean fitness comparison across 3-run stability trial.}
  \label{fig:fitness}
\end{figure}
```

## Required LaTeX Package (IEEEtran)
IEEEtran is included in MiKTeX and TeX Live by default. If missing:
- MiKTeX: will auto-install on first compile
- TeX Live: `tlmgr install IEEEtran`
