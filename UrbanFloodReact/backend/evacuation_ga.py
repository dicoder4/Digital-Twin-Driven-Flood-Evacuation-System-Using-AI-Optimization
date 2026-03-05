"""
evacuation_ga.py
────────────────
Backward-compatible proxy layer. 
The Genetic Algorithm has been modularized into the `genetic_algorithm` folder
for better readability.
"""
from genetic_algorithm import GeneticEvacuationPlanner

__all__ = ["GeneticEvacuationPlanner"]
