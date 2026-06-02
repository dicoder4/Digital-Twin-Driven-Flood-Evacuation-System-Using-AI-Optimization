# Feasibility Analysis: Citizen Evacuation Routing Platform

## Overview of the Proposal
The proposal outlines a citizen-facing platform built on the Digital Twin infrastructure, allowing users to find the safest point-to-point evacuation routes across Bangalore. The core ideas are:
1. Fetch live rainfall from a custom KSNDMC scraping script.
2. Allow citizens to select custom Start and Destination points.
3. Calculate "instant flood" (final progressive state) only for the relevant area based on live rainfall.
4. Calculate the shortest/safest route, and dynamically reroute based on changing floods and traffic.

---

## 1. Map Data Storage: Mongo vs Postgres
> **User Question: Map details and all has to be loaded from mongo/postgres (suggest)**

**Recommendation: PostgreSQL with PostGIS & pgRouting.**
*   **Why not Mongo?** While Mongo has basic 2D sphere indexes, it does not understand road "networks" (nodes connected by edges).
*   **Why Postgres?** PostGIS is the industry standard for geographic data. More importantly, you can use **pgRouting**. You can store the entire Bangalore OSM graph in Postgres. When a user requests a route, you can run an SQL query like: *"Select all road edges within a 2km bounding box of the line between Start and Destination."* It will return this specific "corridor" in milliseconds.

---

## 2. On-Demand "Instant Flood" Calculation
> **User Question: User selects destination... related recent rainfall records are fetched and the flood is calculated (instant flood) on the fly.**

**Verdict: EXTREMELY FEASIBLE (The "Corridor Approach")**
This is a brilliant architectural optimization. Earlier, we established that simulating the *entire city* live takes too long. But if you restrict the simulation to a specific "Corridor", it becomes instant.

**The Workflow:**
1.  User inputs Start (A) and Destination (B).
2.  Backend queries PostGIS to extract a "Corridor Graph" (a bounding box covering A and B + a 1km safety buffer). Instead of 500,000 roads, you now have a tiny graph of maybe 2,000 roads.
3.  Backend fetches the live KSNDMC scraped data (`test_live_scrape.py`) for the Wards/Hoblis that intersect this corridor.
4.  Backend runs the **"Instant Flood"** physics model (steady-state calculation using elevation and live rainfall) *only* on those 2,000 roads.
5.  This takes milliseconds. You now have a live, personalized "Flooded Edges" list for the user's specific journey.

---

## 3. The Routing Engine & Metaheuristics
> **User Question: The route is computed using valhalla, graphrouter, or a specific metaheuristic algo, whichever is the best.**

Since we are using the "Corridor Approach", we actually don't need a heavy global engine like Valhalla.

**Recommended Routing Approach: Python A* (A-Star) or pgRouting**
*   Because you extracted a small corridor graph (e.g., 2,000 nodes) and calculated the flood depths on it in Python, you can simply run an **A* algorithm** directly on that small graph in memory (using NetworkX) or via a pgRouting SQL query.
*   **The Cost Function**: You dynamically calculate the weight of each road: 
    `Cost = (Road_Length / Speed_Limit) + Live_Traffic_Delay + (Flood_Depth * Massive_Penalty)`
*   **Metaheuristics (Genetic Algo / Ant Colony)**: While powerful, metaheuristics are usually "approximate" and computationally heavier. For a single point-to-point route finding the absolute shortest/safest path, A* (or Dijkstra) is mathematically guaranteed to find the absolute best route and will run in <10 milliseconds on a corridor graph. Keep metaheuristics for multi-agent problems (like coordinating 50 ambulances simultaneously).

---

## 4. Rerouting based on Traffic & Changing Floods
> **User Question: Rerouting has to be possible based on traffic and changing flood conditions. Is this possible???**

**Verdict: YES. Fully Possible.**

**The Active Navigation Loop:**
1.  **Traffic Data**: You can integrate an API (like TomTom or Google Maps Traffic API) to fetch live travel times for the corridor.
2.  **The Monitor**: While the citizen is driving, their app sends their GPS coordinate to your backend every 30 seconds.
3.  **The Background Check**: Your `test_live_scrape.py` runs every 5-10 minutes. If it detects that rainfall in the user's current Ward has increased (e.g., from 0mm to 50mm):
    *   The backend triggers a re-calculation of the "Instant Flood" for the remaining corridor.
    *   If the new calculation shows an upcoming road is now flooded, the backend runs A* again from the user's current GPS location.
    *   The backend pushes the new, safe detour to the user's app.

---

## Final Conclusion
Yes, this is completely possible and is actually a highly advanced, optimized architecture. By scraping live KSNDMC data and restricting the flood physics to a **dynamic geographic corridor**, you completely bypass the computational bottleneck of simulating the whole city.

**Next Steps to Build This:**
1.  **Database Migration**: Migrate your OSM graph data from local `.graphml` files into a PostgreSQL/PostGIS database.
2.  **Corridor Extraction API**: Write a function that takes two coordinates, calculates a bounding box, and queries Postgres for all road edges inside it.
3.  **Instant Flood Function**: Adapt your existing Digital Twin physics code to accept this small corridor graph and the live KSNDMC JSON dictionary to output flood depths.
4.  **A* Router**: Implement a simple A* pathfinder that uses the flood depths as weight penalties.
