import pytest
import networkx as nx
from evacuation_ga import GeneticEvacuationPlanner

def test_ga_planner_basic():
    # Setup mock data
    G = nx.Graph()
    G.add_node(1, x=0, y=0)
    G.add_node(2, x=1, y=1)
    
    at_risk_nodes = [
        {'id': 1, 'pop': 100, 'lat': 0.0, 'lon': 0.0}
    ]
    safe_shelters = [
        {'id': 'S1', 'capacity': 200, 'lat': 1.0, 'lon': 1.0}
    ]
    
    planner = GeneticEvacuationPlanner(at_risk_nodes, safe_shelters, G, pop_size=10, generations=5)
    plan = planner.run()
    
    assert len(plan) == 1
    assert plan[0]['from_node'] == 1
    assert plan[0]['to_shelter'] == 'S1'
    assert plan[0]['pop'] == 100
    assert isinstance(plan[0]['path'], list)
    assert len(plan[0]['path']) >= 2
    for coord in plan[0]['path']:
        assert len(coord) == 2

def test_ga_planner_capacity():
    G = nx.Graph()
    for i in range(10): G.add_node(i, x=i, y=i)
    
    at_risk_nodes = [
        {'id': 1, 'pop': 100, 'lat': 0.0, 'lon': 0.0},
        {'id': 2, 'pop': 100, 'lat': 0.1, 'lon': 0.1}
    ]
    safe_shelters = [
        {'id': 'S1', 'capacity': 100, 'lat': 1.0, 'lon': 1.0},
        {'id': 'S2', 'capacity': 100, 'lat': 1.1, 'lon': 1.1}
    ]
    
    planner = GeneticEvacuationPlanner(at_risk_nodes, safe_shelters, G, pop_size=20, generations=10)
    plan = planner.run()
    
    # Check that they aren't both assigned to the same shelter if it violates capacity
    shelter_assignments = {}
    for move in plan:
        sid = move['to_shelter']
        shelter_assignments[sid] = shelter_assignments.get(sid, 0) + move['pop']
    
    for sid, count in shelter_assignments.items():
        assert count <= 100
