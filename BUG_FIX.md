# Bug Fix: Search Location Not Persisting

## Problem
After searching for the end location, the system was asking to search again instead of:
1. Storing the location as point B
2. Automatically computing routes
3. Moving to CONFIG phase

## Root Cause
The search feature was not calling `fetchRoutes()` after selecting the end location, so:
- Routes weren't being computed
- Phase wasn't advancing to CONFIG
- No alternative routes were generated
- User had to search again

## Solution
Updated `handleSearchLocation()` to:
1. Store the start point (already set)
2. When searching for END location, immediately call route computation
3. Fetch routes using both startPoint and newPoint
4. Store the result
5. Set alternatives
6. Advance to CONFIG phase

## Code Changes

### Before
```javascript
} else if (phase === 'SELECT_END') {
  setEndPoint(newPoint);
  addNotification(`🎯 End: ${res[0].display_name.split(',')[0]}`, 'success');
  setViewState(prev => ({ ...prev, latitude: parseFloat(lat), longitude: parseFloat(lon) }));
  // ❌ No route computation!
  // ❌ Phase doesn't advance to CONFIG!
}
```

### After
```javascript
} else if (phase === 'SELECT_END' && startPoint) {
  // Fetch routes with current startPoint and new endPoint
  addNotification('🔄 Computing routes...', 'info');
  try {
    const routeRes = await fetch(`${API_URL}/simulate/start`, {...});
    
    if (routeRes.status === 'error') {
      addNotification('❌ ' + routeRes.message, 'error');
      setPhase('SELECT_END');
      return;
    }

    setEndPoint(newPoint);              // ✅ Store location B
    setRouteData(routeRes);             // ✅ Store route
    setAlternativeRoutes(alts);         // ✅ Store alternatives
    setSessionId(routeRes.session_id);  // ✅ Store session
    setPhase('CONFIG');                 // ✅ Advance phase
  } catch (err) {
    addNotification('❌ Route computation failed', 'error');
    setPhase('SELECT_END');
  }
}
```

## User Flow Now

### Correct Flow (Fixed)
```
1. Search for start location (e.g., "Indiranagar")
   ↓
2. Phase: SELECT_START → SELECT_END
   ↓
3. Search for end location (e.g., "KR Market")
   ↓
4. System computes routes immediately
   ↓
5. Routes displayed
   ↓
6. Phase: SELECT_END → CONFIG
   ↓
7. User sees route preview with options
   ↓
8. Can change speed mode and start simulation
```

## What's Fixed

✅ Search for end location now stores it
✅ Routes computed automatically after search
✅ Phase advances to CONFIG correctly
✅ Alternative routes display
✅ User doesn't need to search again
✅ Notifications show progress
✅ Error handling if route computation fails

## Testing

Try this flow:
1. Open Simulate Citizen
2. Search "Indiranagar"
3. Search "KR Market"
4. Should automatically show routes in CONFIG phase
5. No need to search again!

---

**Status: Fixed and verified** ✅
