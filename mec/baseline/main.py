from datetime import datetime, timezone
from fastapi import FastAPI
from pydantic import BaseModel, Field
import h3

app = FastAPI(title="MEC Autonomous Routing POC")
events = {}

class Hazard(BaseModel):
    event_id: str
    vehicle_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    event_type: str
    severity: float = Field(ge=0, le=1)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "mec-av-poc",
        "stored_events": len(events)
    }

@app.post("/hazards")
def report_hazard(hazard: Hazard):
    cell = h3.latlng_to_cell(
        hazard.latitude, hazard.longitude, 10
    )
    record = {
        **hazard.model_dump(),
        "h3_cell": cell,
        "received_at": datetime.now(timezone.utc).isoformat()
    }
    events[hazard.event_id] = record
    return {"accepted": True, "event": record}

@app.get("/hazards")
def list_hazards():
    return {"events": list(events.values())}
