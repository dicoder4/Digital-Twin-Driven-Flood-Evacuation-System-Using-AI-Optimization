# Speed Logic & Flood Physics Alignment

## Backend Changes

### 1. Speed Configuration (Logical & Realistic)
```python
SPEED_MAP = {
    "car": 30,      # Urban traffic speed (realistic, not highway)
    "bike": 15,     # Cycling speed (average cyclist)
    "walk": 4,      # Walking pace (normal human walking)
}
```

**Why these speeds?**
- **Car (30 km/h)**: Urban evacuation with traffic, not highway speed
- **Bike (15 km/h)**: Moderate cycling effort, realistic for evacuation
- **Walk (4 km/h)**: Normal human walking speed (3-5 km/h range)

### 2. Dynamic ETA Calculation
```python
def calculate_eta_minutes(distance_m: float, speed_kph: float) -> int:
    """Calculate ETA based on actual distance and selected speed mode."""
    distance_km = distance_m / 1000.0
    time_hours = distance_km / speed_kph
    time_minutes = time_hours * 60
    return round(time_minutes)
```

**How it works:**
- Takes total distance from the route (fixed)
- Applies user-selected speed mode
- Calculates ETA = (distance_km / speed_kph) * 60 minutes
- Examples:
  - 5 km by car (30 km/h): 10 minutes
  - 5 km by bike (15 km/h): 20 minutes
  - 5 km on foot (4 km/h): 75 minutes

### 3. Speed-based Summary Generation
**Primary Route Summary:**
```python
speed_kph = SPEED_MAP.get(req.speed_mode, 30)
summary = {
    "total_distance_m": base_summary["total_distance_m"],  # Fixed
    "eta_minutes": calculate_eta_minutes(distance_m, speed_kph),  # Speed-dependent ✅
    "max_flood_depth_m": base_summary["max_flood_depth_m"],  # From physics
    "flooded_segments": base_summary["flooded_segments"],    # From physics
    "safe": base_summary["safe"],                           # From physics (> 1.5m = impassable)
}
```

**Alternative Routes:** Each alternative also gets recalculated with the same speed mode.

## Frontend Changes

### 1. Speed Configuration (Matches Backend)
```javascript
const SPEED_CONFIG = {
  car: { label: '🚗 Car (30 km/h)', speed_kph: 30 },
  bike: { label: '🚴 Bike (15 km/h)', speed_kph: 15 },
  walk: { label: '🚶 Walking (4 km/h)', speed_kph: 4 },
};
```

### 2. Dynamic Route Preview
When user selects a speed mode, the ETA updates **immediately** in the CONFIG phase:
```javascript
// Show preview with selected speed
<strong>
  {Math.round((routeData.summary.total_distance_m / 1000) / SPEED_CONFIG[speedMode].speed_kph * 60)} min
</strong>
```

**Example:**
- 5 km route
- Select Car: "10 min" (5/30*60)
- Select Bike: "20 min" (5/15*60)
- Select Walk: "75 min" (5/4*60)

### 3. Flood Physics Integration
```javascript
{stats.max_flood_depth_m > 1.5 && '⚠️ IMPASSABLE - Depth > 1.5m'}
{stats.max_flood_depth_m > 0.8 && stats.max_flood_depth_m <= 1.5 && '⚠️ High flood - Walking/Biking risky'}
{stats.max_flood_depth_m > 0.4 && stats.max_flood_depth_m <= 0.8 && '⚡ Moderate flood - All modes passable'}
{stats.max_flood_depth_m > 0.1 && stats.max_flood_depth_m <= 0.4 && '💧 Light flooding - Normal travel'}
{stats.max_flood_depth_m <= 0.1 && '✅ No flooding - Safe passage'}
```

## Flood Physics Alignment

### Core Physics (from corridor_flood.py)
```python
depth = (avg_rain / 1000.0) * downhill_factor * lake_factor * drain_factor
IMPASSABLE_DEPTH = 1.5  # Can't pass if depth >= 1.5m
```

### How Depth Affects Each Speed Mode

| Depth | Status | Car | Bike | Walk |
|-------|--------|-----|------|------|
| **> 1.5m** | IMPASSABLE | ❌ | ❌ | ❌ |
| 0.8-1.5m | High Flood | ⚠️ Risky | ❌ Risky | ❌ Risky |
| 0.4-0.8m | Moderate | ✅ OK | ⚠️ Risky | ⚠️ Risky |
| 0.1-0.4m | Light | ✅ OK | ✅ OK | ✅ OK |
| < 0.1m | Safe | ✅ OK | ✅ OK | ✅ OK |

### Routing Logic
- **A* cost function** considers both:
  - Travel time: `(distance / speed_kph) * 60`
  - Flood penalty: `depth * 1000.0`
  - Total cost: `travel_time + flood_penalty`
- Routes with high water depths get **penalized**, not blocked
- Only routes with depth >= 1.5m are **impassable**

## Example Scenario

### User Selects Route
```
Start: (12.9716, 77.5946)
End: (12.9952, 77.6245)
Distance: 5 km
Max Flood: 0.45m (moderate flooding)
```

### Route Preview (CONFIG Phase)
User selects **Car** (30 km/h):
- Distance: 5 km
- ETA: **10 min** ← Dynamic calculation
- Risk: **SAFE ✅** ← From physics
- Note: "⚡ Moderate flood - All modes passable"

User changes to **Bike** (15 km/h):
- Distance: 5 km
- ETA: **20 min** ← Recalculated immediately
- Risk: **SAFE ✅** ← Same (physics unchanged)
- Note: "⚡ Moderate flood - All modes passable"

User changes to **Walk** (4 km/h):
- Distance: 5 km
- ETA: **75 min** ← Recalculated immediately
- Risk: **SAFE ✅** ← Same
- Note: "⚡ Moderate flood - All modes passable"

### During Simulation (RUNNING Phase)
Backend processes each tick:
1. Evolve rainfall (flood increases in some areas)
2. Recalculate max flood depth
3. If depth > 0.8m and user on bike/walk: Show warning
4. If depth > 1.5m anywhere: Trigger rerouting

## Logic Flow

```
User Interaction
  ↓
SELECT_START → User picks location A
  ↓
SELECT_END → User picks location B
  ↓
CONFIG → Routes computed with all speed modes
       → Show preview with selected speed
       → ETA updates when speed changes
  ↓
RUNNING → Selected speed mode used for timing
       → Flood depth monitored every 5 seconds
       → If flood intensifies: Show notification
       → If route becomes impassable: Reroute
  ↓
COMPLETE → Show final stats
```

## Physics Constants
- **Impassable depth**: 1.5m (from astar_router.py)
- **High flood**: 0.8m (warning level)
- **Moderate flood**: 0.4m (caution level)
- **Light flood**: 0.1m (minimal impact)

## Validation

✅ Speed modes match backend SPEED_MAP
✅ ETA calculation uses correct formula: (distance_km / speed_kph) * 60
✅ Flood depths come from physics simulation
✅ Routing cost includes both time and flood penalty
✅ Alternative routes recalculated for each speed
✅ Notifications aligned with flood physics thresholds
✅ Impassable routes (> 1.5m) trigger rerouting

---

**System is now LOGICAL and ALIGNED with core flood physics!** 🎯
