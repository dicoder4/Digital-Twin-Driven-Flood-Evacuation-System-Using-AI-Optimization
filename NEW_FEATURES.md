# New Features Added

## 1. Location Search

### How It Works
- User types location name in search box
- Presses Enter or clicks 🔍 button
- System queries OSM Nominatim geocoding API
- Auto-zooms to searched location
- Sets marker at found coordinates

### Example Usage
```
User types: "Kempegowda International Airport"
System finds: 13.1968° N, 77.7064° E
Map zooms to location
Marker A placed at airport
```

### Search Features
- Works for both START and DESTINATION
- Bounded search around current map view
- Returns top 5 results, uses first match
- Shows result name in notification
- Auto-zoom to result (helps user verify)

---

## 2. Tap to Unselect (Double-Click)

### How It Works
- User double-clicks on marker (A or B)
- Marker is removed
- Phase resets to allow new selection
- Notification shows marker cleared

### Implementation
```javascript
onDoubleClick={() => handleClearMarker('start')}
// or
onDoubleClick={() => handleClearMarker('end')}
```

### User Flow
```
User sees marker A on map
Wants to change starting location
Double-clicks marker A
→ Marker disappears
→ Phase returns to SELECT_START
→ Can now tap map to place new start point
```

### Visual Feedback
- Marker shows tooltip: "Double-click to remove"
- Clear notification: "❌ Start point cleared"

---

## 3. Draggable Location Pins

### How It Works
- User clicks and drags marker (A or B)
- Marker follows cursor smoothly
- Updates coordinates in real-time
- Marker highlights during drag (yellow glow)
- Can fine-tune location without re-tapping

### Drag Features
```javascript
// Marker states:
draggable           // Can be dragged
onDragStart         // Highlight, set cursor to 'grabbing'
onDrag              // Follow mouse, update coordinates
onDragEnd           // Release, unhighlight
```

### Visual Changes During Drag
```
Normal state:
  Border: 3px white
  Shadow: Standard blue glow
  Cursor: grab

Dragging state:
  Border: 4px yellow (#fbbf24)
  Shadow: Yellow glow expanding
  Cursor: grabbing
  Size: Slightly larger feel
```

### User Flow
```
User places marker at A
Realizes it's slightly off
Clicks and drags A to fine position
→ Yellow glow shows it's being dragged
→ Marker follows cursor
→ Release to drop at new location
→ Coordinates update in UI
```

---

## Implementation Details

### State Management
```javascript
const [draggedMarker, setDraggedMarker] = useState(null);  // 'start', 'end', or null
const markerStartRef = useRef({ lat: 0, lon: 0 });       // Initial position when drag starts
```

### Marker Component Changes
```javascript
<Marker
  longitude={startPoint.lon}
  latitude={startPoint.lat}
  draggable                           // ← Enable dragging
  onDragStart={() => handleMarkerDragStart('start')}
  onDrag={(e) => handleMarkerDrag(e, 'start')}
  onDragEnd={() => handleMarkerDragEnd('start')}
  title="Drag to move, double-click to remove"
>
  {/* Styled div with drag states */}
</Marker>
```

### User Helpers
- **Tooltip**: "Drag to move, double-click to remove"
- **Cursor feedback**: `grab` → `grabbing`
- **Visual feedback**: Glow expands during drag
- **Search box**: Always available in SELECT phases

---

## Complete User Flow

### Scenario 1: Using Search
```
1. User opens Simulate Citizen
2. Panel shows "TAP MAP OR SEARCH START"
3. User types "BTM Layout" in search
4. Presses Enter
5. Map zooms to BTM Layout
6. Marker A placed at coordinates
7. User clicks panel back button or taps for destination
8. Repeat for destination
9. Routes computed automatically
```

### Scenario 2: Using Drag to Fine-Tune
```
1. User taps on map to place start point
2. Marker A appears, but slightly off
3. User clicks and drags marker A
4. Marker shows yellow glow and follows cursor
5. User drags to exact position
6. Releases - marker placed
7. Coordinates update in UI (automatic)
8. Routes recomputed with new location
```

### Scenario 3: Removing and Replacing
```
1. User has markers A and B
2. Realizes A is wrong location
3. Double-clicks marker A
4. Marker disappears, phase returns to SELECT_START
5. User either:
   a) Taps new location on map, OR
   b) Searches for location name
6. New marker placed
7. Routes computed
```

---

## UI/UX Features

### Search Box
- Available in SELECT_START and SELECT_END phases
- Placeholder text changes based on phase
- Enter key triggers search
- Search button with 🔍 icon
- Results show in notification system

### Coordinates Display
- Shows in monospace font for clarity
- Updates in real-time during drag
- Formatted to 4 decimal places (~11m precision)
- Shows hint text about dragging/double-click

### Visual Feedback
- Marker highlights during drag
- Glow effect expands
- Cursor changes (grab ↔ grabbing)
- Tooltips on hover

### Notifications
- Search starting: "🔍 Searching location..."
- Search success: "✅ Start: Location Name"
- Search failure: "❌ Location not found"
- Marker cleared: "❌ Start point cleared"

---

## Technical Implementation

### Geocoding API
- Endpoint: `/citizen/geocode` (already exists)
- Uses: OSM Nominatim
- Bounds: Bounded to map view for relevance
- Returns: Top 5 results, uses first

### Marker Dragging
- Uses MapLibre `draggable` property
- Handlers: onDragStart, onDrag, onDragEnd
- Prevents map click while dragging: `if (draggedMarker) return;`
- Real-time coordinate updates

### State Consistency
- Search input cleared after search
- Marker state updates immediately
- Routes recomputed with new coordinates
- No lag in visual feedback

---

## Files Modified

- `UrbanFloodReact/frontend/src/components/SimulateCitizenView.jsx`
  - Added `handleSearchLocation()` function
  - Added `handleMarkerDragStart/Drag/DragEnd()` functions
  - Added `handleClearMarker()` function
  - Updated marker components with drag handlers
  - Added search UI in SELECT phases
  - Added state: `searchQuery`, `draggedMarker`

---

## Checklist

✅ Search and select location (with geocoding)
✅ Tap to unselect (double-click markers)
✅ Draggable location pins
✅ Real-time coordinate updates
✅ Visual feedback during operations
✅ User hints and tooltips
✅ Notification system integration
✅ All three features working seamlessly

**Status: Complete and tested** 🎯
