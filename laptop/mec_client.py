"""Client for the actual /hazards contract, with explicit POC semantics."""
import hashlib
import json
import time
from urllib.parse import urlparse

import h3
import httpx
from pydantic import BaseModel, ConfigDict, Field

SEMANTIC_FIELDS = ("event_id", "vehicle_id", "latitude", "longitude", "event_type", "severity")
EVENT_TYPES = {"warning": "alivemap.warning", "closed": "alivemap.closed", "clear": "alivemap.clear"}


class HazardRecord(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    event_id: str
    vehicle_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    event_type: str
    severity: float = Field(ge=0, le=1)
    h3_cell: str
    received_at: str


def revision(events):
    """Content revision, excluding receipt timestamps; not a MEC sequence counter."""
    semantic = [{key: event[key] for key in SEMANTIC_FIELDS} for event in events]
    semantic.sort(key=lambda event: event["event_id"])
    return hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class MecClient:
    def __init__(self, url, run, network_id, http=None, semantics_url=None):
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("Use the loopback URL of an SSH local forward")
        self.prefix = f"alivemap:{network_id}:{run}:"
        self.http = http or httpx.Client(base_url=url.rstrip("/"), timeout=5, trust_env=False,
                                         limits=httpx.Limits(max_keepalive_connections=0))
        self.semantics_url = semantics_url
        if semantics_url:
            parsed = urlparse(semantics_url)
            if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
                raise ValueError("Semantic view must also use an SSH loopback forward")
        self.acknowledged_ids = set()
        self.attempted_report = False
        self.last_revision = revision([])
        self.change_number = 0

    def preflight(self, expected_schema):
        response = self.get("/health")
        if response.json().get("service") != "mec-av-poc":
            raise ValueError("Forward does not reach the inspected MEC service")
        response = self.get("/openapi.json")
        if response.json() != expected_schema:
            raise ValueError("Running API schema differs from the reviewed baseline")

    def get(self, path, **kwargs):
        """Retry a lost/5xx read once; never manufacture an empty state."""
        for attempt in range(2):
            try:
                response = self.http.get(path, **kwargs)
                response.raise_for_status()
                return response
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise
                if attempt == 1:
                    raise
                time.sleep(0.15)

    def report(self, state, lat, lon):
        payload = dict(event_id=self.prefix + "demo-road", vehicle_id="probe",
                       latitude=lat, longitude=lon, event_type=EVENT_TYPES[state],
                       severity={"warning": 0.7, "closed": 1.0, "clear": 0.0}[state])
        return self.post_payload(payload)

    def post_payload(self, payload):
        """Shared acknowledged transport; retain the inspected six-field API."""
        self.attempted_report = True
        for attempt in range(3):
            try:
                response = self.http.post("/hazards", json=payload)
                response.raise_for_status()
                body = response.json()
                if body.get("accepted") is not True:
                    raise ValueError("MEC did not acknowledge the report")
                event = self.validate(body["event"])
                if any(event[key] != value for key, value in payload.items()):
                    raise ValueError("MEC acknowledged different report contents")
                self.acknowledged_ids.add(payload["event_id"])
                return payload, body
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise
                if attempt == 2:
                    raise RuntimeError("Report unacknowledged after three attempts") from exc
                time.sleep(0.2 * (attempt + 1))

    @staticmethod
    def validate(raw):
        event = HazardRecord.model_validate(raw).model_dump()
        expected = h3.latlng_to_cell(event["latitude"], event["longitude"], 10)
        if event["h3_cell"] != expected:
            raise ValueError("MEC H3 cell does not match coordinates at resolution 10")
        return event

    def all_events(self):
        response = self.get("/hazards")
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("events"), list):
            raise ValueError("Expected the real MEC's {events: [...]} response")
        return body["events"]

    def snapshot(self):
        if self.semantics_url:
            response = self.get(self.semantics_url, params={"prefix": self.prefix})
            body = response.json()
            if body.get("schema_version") != 1 or body.get("prefix") != self.prefix:
                raise ValueError("Semantic view returned an unexpected schema or prefix")
            raw_events = body["events"]
            if body.get("revision") != revision(raw_events):
                raise ValueError("Semantic view revision does not describe its events")
        else:
            raw_events = self.all_events()
        events = [self.validate(event) for event in raw_events
                  if isinstance(event, dict) and str(event.get("event_id", "")).startswith(self.prefix)]
        ids = [event["event_id"] for event in events]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate event ID in MEC snapshot")
        if not self.acknowledged_ids.issubset(ids):
            raise RuntimeError("Acknowledged MEC state disappeared; possible API restart. Stop rather than infer clear.")
        if any(event["event_type"] not in EVENT_TYPES.values() for event in events):
            raise ValueError("Unrecognized semantic event type in this run")
        current = revision(events)
        if current != self.last_revision:
            self.change_number += 1
            self.last_revision = current
        return {"version": self.change_number, "revision": current, "hazards": events}

    def close(self):
        self.http.close()
