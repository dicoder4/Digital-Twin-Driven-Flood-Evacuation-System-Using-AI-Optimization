import asyncio
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter

class AutoConfig(BaseModel):
    active: bool
    hobli: str
    threshold_mm: float

class AutomationState:
    active: bool = False
    hobli: str = "Uttarahalli-1"
    threshold_mm: float = 10.0
    trigger_simulation: bool = False
    logs: list = []

    @classmethod
    def log(cls, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        cls.logs.append(f"[{ts}] {msg}")
        if len(cls.logs) > 50:
            cls.logs.pop(0)

def _find_hobli_info(hobli_name: str) -> dict:
    from region_manager import HOBLI_COORDS, norm_key
    search_key = norm_key(hobli_name)
    if search_key in HOBLI_COORDS:
        info = HOBLI_COORDS[search_key]
        return {"lat": info["lat"], "lon": info["lon"], "display": info.get("original_name", hobli_name)}
    for k, info in HOBLI_COORDS.items():
        if norm_key(info.get("original_name", "")) == search_key:
            return {"lat": info["lat"], "lon": info["lon"], "display": info.get("original_name", hobli_name)}
    return None

async def weather_watcher_loop():
    AutomationState.log("Sentinel daemon initialized.")
    while True:
        await asyncio.sleep(5)  # Fast poll for presentation responsiveness
        if not AutomationState.active:
            continue
            
        try:
            h_info = _find_hobli_info(AutomationState.hobli)
            if not h_info:
                AutomationState.log(f"Hobli '{AutomationState.hobli}' not found in registry.")
                AutomationState.active = False
                continue
                
            from genai.weather_client import WeatherClient
            client = WeatherClient.from_hobli_info(h_info)
            
            loop = asyncio.get_event_loop()
            weather = await loop.run_in_executor(None, client.get_current)
            
            precip = weather.get("precipitation_mm", 0.0)
            desc = weather.get("description", "Clear")
            
            AutomationState.log(f"Live scan - {AutomationState.hobli}: {precip}mm ({desc})")
            
            if precip >= AutomationState.threshold_mm:
                AutomationState.log(f"🚨 THRESHOLD EVENT ({precip} >= {AutomationState.threshold_mm}mm)!")
                AutomationState.log("Firing Autonomous Evacuation Pipeline...")
                AutomationState.trigger_simulation = True
                AutomationState.active = False  # Auto-disable after trigger to prevent loops
            else:
                AutomationState.log("Conditions Nominal.")
                
            await asyncio.sleep(15)  # Rest before next external API ping
        except Exception as e:
            AutomationState.log(f"API Connect Error: {str(e)}")
            await asyncio.sleep(10)

router = APIRouter()

@router.get("/automation/status")
async def get_auto_status():
    trig = AutomationState.trigger_simulation
    if trig:
        AutomationState.trigger_simulation = False
    return {
        "active": AutomationState.active,
        "hobli": AutomationState.hobli,
        "threshold_mm": AutomationState.threshold_mm,
        "trigger_simulation": trig,
        "logs": AutomationState.logs
    }

@router.post("/automation/config")
async def set_auto_config(conf: AutoConfig):
    AutomationState.active = conf.active
    AutomationState.hobli = conf.hobli
    AutomationState.threshold_mm = conf.threshold_mm
    AutomationState.trigger_simulation = False
    if conf.active:
        AutomationState.log(f"ARMED: Sentinel watching {conf.hobli} > {conf.threshold_mm}mm.")
    else:
        AutomationState.log("DISARMED: Sentinel offline.")
    return {"status": "ok"}
