Official Occupancy Capacity Formula for Bengaluru, India
In Bengaluru (and all of India), occupancy capacity is governed by the National Building Code of India 2016 (NBC 2016), Part 4: Fire and Life Safety, enforced by the Karnataka State Fire & Emergency Services (KSFES).

The Formula
text
Occupant Load (persons) = Usable Floor Area (m²) ÷ Occupant Load Factor (m²/person)
Where:

Usable Floor Area = Total floor area minus corridors, stairways, toilets, mechanical rooms, shafts, and fixed equipment

Occupant Load Factor = Value from NBC 2016 Table 12.1 based on occupancy type

Final Capacity = Lesser of:

Floor area calculation (above), AND

Exit capacity based on door/stair width (0.5 m per 100 persons for level exits; 0.75 m per 100 persons for stairs)

NBC 2016 Table 12.1: Occupant Load Factors (India)
Occupancy Type	Use/Sub-division	Load Factor (m²/person)	Load Factor (ft²/person)
Assembly (Group E)			
Standing space (no fixed seats)	Concerts, cocktail parties	0.65	7
Fixed seating	Auditoriums, theatres, cinemas	1.2 × seat count	~13
Waiting spaces	Lobbies, corridors	1.4	15
Residential (Group A)			
Dwelling units	Flats, apartments, houses	12.5	135
Hostels/Dormitories	Hostels, PG accommodations	6.5	70
Educational (Group C)			
Classrooms	Schools, colleges	4.0	43
Laboratories/Workshops	Vocational training, ITI	10.0	108
Healthcare (Group D)			
OPD/Outdoor areas	Clinics, dispensaries	10.0	108
IPD/Indoor patient areas	Hospitals, nursing homes	15.0	161
Business (Group I)			
Offices	IT parks, corporate offices	10.0	108
Mercantile (Group H)			
Ground floor retail	Malls, shops	3.0	32
Upper floor retail	Malls, showrooms	6.0	65
Storage areas	Godowns (not public)	30.0	323
Industrial (Group J)			
Manufacturing floors	Factories	10.0	108
Transportation (Group F)			
Passenger terminals	Bus stands, metro stations	3.0	32
Sources: NBC 2016 Part 4, Table 12.1 

Example Calculation (Bengaluru Office)
For a 500 m² IT office floor in Whitefield:

text
Occupant Load = 500 m² ÷ 10.0 m²/person = 50 persons
If the floor has two exits each 1.2 m wide:

Exit capacity = (1.2 + 1.2) m ÷ 0.005 m/person = 480 persons

Final capacity = 50 persons (limited by floor area, not exits)

Key Compliance Points for Bengaluru
Fire NOC mandatory: All buildings >15 m height or >500 m² floor area need Karnataka Fire Service clearance before occupancy

Exit width rule: Minimum 0.5 m width per 100 persons for level exits; 0.75 m per 100 for stairs

Travel distance limits: Max 30 m to nearest exit for most occupancies; 22.5 m for high-hazard areas

No exceeding allowed: The calculated capacity is a legal maximum—exceeding it violates the Karnataka Fire Safety Act and can result in fines, seal orders, or criminal liability. Does this Formula and the 3-Tier logic make sense to you? If you approve, I can begin implementing this into the `BaseEvacuationPlanner`.

---

## 4. Implementation Details: OSM Footprint Integration & NBC Guidelines

To supply accurate Base Capacities to the formula above, the Physical Layer of the simulation has been upgraded:

1. **True Physical Area Logging ($m^2$)**:
   The Shelter Generator now projects all raw OpenStreetMap coordinates into the local **UTM (Universal Transverse Mercator)** coordinate system. This lets the backend calculate the precise square-meter area (`area_sqm`) of every building.

2. **Footprint Linkage**:
   If OSM maps a school as just a "Point" with zero area, the engine runs a secondary spatial query to scan all nearby building polygons. It performs a **Spatial Join (Intersection)** to find the exact building footprint the point rests on, granting it a real-world area.

3. **NBC 2016 Fire Safety Integration**:
   Rather than guessing a building's capacity, the $m^2$ area is processed through the **National Building Code of India (NBC 2016)** Load Factors.
   - **Formula**: `Capacity = (Gross Area * 0.8) / Occupant_Load_Factor`
   - *Example*: A 1,000 $m^2$ school uses an $0.8$ usable-space ratio and an NBC Educational Load Factor of $4.0 m^2/\text{person}$. 
   - `Capacity = 800 / 4.0 = 200 people (Base Safe Capacity)`.

For custom calculations or layout changes, you must get approval from Karnataka State Fire & Emergency Services (ksfes.karnataka.gov.in).
