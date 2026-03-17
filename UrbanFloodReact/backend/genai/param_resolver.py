import sys
import os

# Add the parent directory (backend) to the python path so it can import region_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from region_manager import HOBLI_COORDS, norm_key, initialise

def resolve_hobli(hobli_name: str) -> dict:
    """
    Resolve a given hobli name to its coordinates and normalized info.
    Returns None if not found.
    """
    if not HOBLI_COORDS:
        initialise()
        
    key = norm_key(hobli_name)
    coords = HOBLI_COORDS.get(key)
    
    if not coords:
        return None
        
    return {
        "display": hobli_name,
        "key": key,
        "lat": coords["lat"],
        "lon": coords["lon"]
    }
