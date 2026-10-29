"""Additive loopback MEC playground service; never imports SUMO or computes routes.

H3 processing and tower-scoped semantic fan-out execute here, not in the map UI.
Tower coverage is explicitly a synthetic circular association model, not RF/5G proof.
Run separately: python -m uvicorn mec.playground_api:app --host 127.0.0.1 --port 8767
"""
import hashlib
import json
import math
import os
import sqlite3
import secrets
from datetime import datetime, timedelta, timezone
from threading import RLock
from urllib.request import Request, urlopen, build_opener, ProxyHandler
from urllib.error import HTTPError
from uuid import UUID
from pathlib import Path

import h3
from fastapi import FastAPI, HTTPException, Request as HttpRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

SERVICE = "alivemap-playground-mec"
ROLES = {"reporter", "receiver", "both", "offline"}


def utc():
    return datetime.now(timezone.utc).isoformat()


def distance(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    value = math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371008.8*2*math.asin(min(1, math.sqrt(value)))


def point_in_bounds(point, bounds):
    return all(math.isfinite(v) for v in point) and bounds[0] <= point[0] <= bounds[2] and bounds[1] <= point[1] <= bounds[3]


def validate_geometry(geometry, bounds):
    if geometry.get("type") != "Polygon" or len(geometry.get("coordinates", [])) != 1:
        raise ValueError("Use a Polygon with one exterior ring")
    ring = geometry["coordinates"][0]
    if not 4 <= len(ring) <= 130 or ring[0] != ring[-1] or any(len(p) != 2 or not point_in_bounds(p, bounds) for p in ring):
        raise ValueError("Polygon needs 3–129 vertices, closed and inside this map")
    def cross(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def intersects(a, b, c, d):
        if max(a[0], b[0]) < min(c[0], d[0]) or max(c[0], d[0]) < min(a[0], b[0]) or max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1]):
            return False
        return cross(a, b, c)*cross(a, b, d) <= 0 and cross(c, d, a)*cross(c, d, b) <= 0
    for i in range(len(ring)-1):
        if ring[i] == ring[i+1]:
            raise ValueError("Repeated polygon vertex")
        for j in range(i+2, len(ring)-1):
            if i == 0 and j == len(ring)-2:
                continue
            if intersects(ring[i], ring[i+1], ring[j], ring[j+1]):
                raise ValueError("Polygon must not intersect itself")
    area = abs(sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(ring, ring[1:])))/2
    area_m2 = area*111320**2*math.cos(math.radians(ring[0][1]))
    if not 1 <= area_m2 <= 25_000_000:
        raise ValueError("Incident area must be between 1 m² and 25 km²")
    return ring


def affected_cells(geometry):
    polygon = h3.geo_to_h3shape(geometry)
    cells = {str(res): sorted(h3.h3shape_to_cells_experimental(polygon, res, contain="overlap")) for res in (8, 10)}
    if len(cells["10"]) > 4000:
        raise ValueError("Incident covers too many H3 cells; use a smaller area")
    return cells


def assess(kind,facts,reporters):
    """Transparent POC risk policy, computed only by the selected MEC backend."""
    severity=0 if kind=='clear' else 1 if kind=='landslide' else min(1,facts.get('water_depth_m',0)/.5) if kind=='flood' else 1-facts.get('traffic_speed_ratio',1)
    count=len(set(reporters)-{'operator'})
    return {'severity':round(severity,3),'priority':'cleared' if kind=='clear' else 'critical' if severity>=.8 else 'high' if severity>=.4 else 'moderate',
            'independent_reporters':count, 'confidence':'corroborated' if count>=2 else 'single report' if count else 'operator injection',
            'policy':'POC rules: closure=1; flood=depth/0.5m capped at 1; congestion=1-speed ratio'}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Tower(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-85, le=85)
    radius_m: float = Field(ge=50, le=10000)


class Experiment(StrictModel):
    experiment_id: UUID
    map_id: str = Field(min_length=1, max_length=80)
    bounds: tuple[float, float, float, float]
    towers: list[Tower] = Field(max_length=32)


class TelemetryVehicle(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-85, le=85)
    role: str


class Tick(StrictModel):
    sim_time: float = Field(ge=0)
    vehicles: list[TelemetryVehicle] = Field(max_length=64)


class SensorReport(StrictModel):
    incident_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    vehicle_id: str = Field(min_length=1, max_length=64)
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-85, le=85)
    kind: str
    geometry: dict
    facts: dict = Field(default_factory=dict)
    event_version: int = Field(ge=1)
    ttl_s: float = Field(default=1800, ge=1, le=86400)
    source_type: str = "simulated_perception"


def create_app(legacy_post=None, state_path=None, api_key=None, legacy_http=None):
    app = FastAPI(title="AliveMap MEC Playground", version="1.0")
    api_key = api_key or os.environ.get('ALIVEMAP_API_KEY')
    if api_key and len(api_key) < 32:
        raise ValueError('Configured API key must contain at least 32 characters')

    @app.middleware('http')
    async def authenticate(request, call_next):
        supplied = request.headers.get('Authorization', '')
        if api_key and not secrets.compare_digest(supplied.encode(), ('Bearer '+api_key).encode()):
            return JSONResponse({'detail': 'Authentication required'}, status_code=401,
                                headers={'WWW-Authenticate': 'Bearer'})
        return await call_next(request)
    experiments, lock = {}, RLock()
    app.state.experiments = experiments
    database = None
    state_path = state_path or os.environ.get('ALIVEMAP_STATE_DB')
    if state_path:
        path = Path(state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        database = sqlite3.connect(path, check_same_thread=False)
        database.execute('PRAGMA journal_mode=WAL')
        database.execute('PRAGMA synchronous=FULL')
        version = database.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            raise ValueError('Unsupported playground state database schema; refusing to overwrite')
        database.execute('CREATE TABLE IF NOT EXISTS experiments (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        database.execute('PRAGMA user_version=1')
        database.commit()
        for eid, body in database.execute('SELECT id, body FROM experiments'):
            ctx = json.loads(body)
            ctx['delivered'] = {name: set(ids) for name, ids in ctx['delivered'].items()}
            experiments[eid] = ctx
    app.state.database = database

    def persist(ctx):
        if database:
            data = {**ctx, 'delivered': {name: sorted(ids) for name, ids in ctx['delivered'].items()}}
            with database:
                database.execute('INSERT INTO experiments(id,body) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                                 (ctx['id'], json.dumps(data, separators=(',', ':'))))

    def legacy(payload):
        if legacy_post:
            return legacy_post(payload)
        url = os.environ.get("ALIVEMAP_LEGACY_URL", "http://127.0.0.1:8765").rstrip("/")+"/hazards"
        request = Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def context(eid):
        if eid not in experiments:
            raise HTTPException(404, "Unknown or closed experiment")
        return experiments[eid]

    def associate(point, towers):
        candidates = [(distance(point, (t["longitude"], t["latitude"])), t["id"]) for t in towers]
        candidates = [(d, tid) for d, tid in candidates if d <= next(t["radius_m"] for t in towers if t["id"] == tid)]
        return min(candidates)[1] if candidates else None

    def snapshot(ctx):
        now = datetime.now(timezone.utc)
        for incident in ctx["incidents"].values():
            if incident["status"] == "active" and now >= datetime.fromisoformat(incident["observation"]["expires_at"]):
                incident["status"] = "expired"
        deliveries, associations = {}, {}
        for vehicle in ctx["vehicles"].values():
            point = vehicle["longitude"], vehicle["latitude"]
            tower_id = None if vehicle["role"] == "offline" else associate(point, ctx["towers"])
            associations[vehicle["id"]] = {"tower_id": tower_id, "h3_cell": h3.latlng_to_cell(point[1], point[0], 10)}
            received = []
            if tower_id and vehicle["role"] in ("receiver", "both"):
                tower = next(t for t in ctx["towers"] if t["id"] == tower_id)
                known_ids = ctx["delivered"].setdefault(vehicle["id"], set())
                for incident in ctx["incidents"].values():
                    # Fan-out via serving towers whose coverage intersects an affected
                    # H3 cell. Relevance is computed on MEC, without vehicle routes.
                    relevant = any(distance((tower["longitude"], tower["latitude"]), tuple(reversed(h3.cell_to_latlng(cell)))) <= tower["radius_m"]+h3.average_hexagon_edge_length(10, unit="m")*2
                                   for cell in incident["h3_cells"]["10"])
                    # Corrections/clearance must also reach previously informed
                    # vehicles after a handover or incident geometry edit.
                    if relevant or incident["id"] in known_ids:
                        received.append(incident)
                        known_ids.add(incident["id"])
            deliveries[vehicle["id"]] = received
        persist(ctx)
        return {"experiment_id": ctx["id"], "map_id": ctx["map_id"], "sim_time": ctx["sim_time"],
                "towers": ctx["towers"], "associations": associations, "incidents": list(ctx["incidents"].values()),
                "deliveries": deliveries, "transport": "HTTP polling; tower-scoped application fan-out is simulated, not RF broadcast"}

    @app.get("/health")
    def health():
        return {"status": "ok", "service": SERVICE, "schema_version": 1, "delivery_revision": 2, "experiments": len(experiments),
                'story_revision':1,
                "h3_version": h3.__version__, "state_storage": "sqlite" if database else "memory",
                "authentication": "bearer" if api_key else "loopback-only",
                "coverage_model": "synthetic nearest tower within circular radius"}

    @app.api_route('/legacy/{resource}', methods=['GET', 'POST'])
    async def compatibility(resource: str, request: HttpRequest):
        # Preserve older guided/grid controllers through the same authenticated
        # endpoint. Only these reviewed baseline routes may be forwarded.
        if resource not in ('health', 'openapi.json', 'hazards'):
            raise HTTPException(404, 'Unknown compatibility route')
        if request.method == 'POST' and resource != 'hazards':
            raise HTTPException(405, 'Method not supported')
        body = await request.body() if request.method == 'POST' else None
        if legacy_http is not None:
            response = legacy_http.request(request.method, '/'+resource, content=body,
                                           headers={'Content-Type': 'application/json'})
            return JSONResponse(response.json(), status_code=response.status_code)
        url = os.environ.get('ALIVEMAP_LEGACY_URL', 'http://127.0.0.1:8765').rstrip('/')+'/'+resource
        from asyncio import to_thread
        def forward():
            outgoing = Request(url, data=body, method=request.method, headers={'Content-Type': 'application/json'})
            try:
                with build_opener(ProxyHandler({})).open(outgoing, timeout=5) as response:
                    return JSONResponse(json.load(response), status_code=response.status)
            except HTTPError as exc:
                return JSONResponse(json.load(exc), status_code=exc.code)
            except OSError as exc:
                raise HTTPException(502, 'Original baseline API unavailable') from exc
        return await to_thread(forward)

    @app.post("/v1/experiments")
    def register(body: Experiment):
        eid = str(body.experiment_id)
        w, s, e, n = body.bounds
        if not (-180 <= w < e <= 180 and -85 <= s < n <= 85 and e-w <= 2 and n-s <= 2):
            raise HTTPException(422, "Invalid compact map bounds")
        towers = [t.model_dump() for t in body.towers]
        if len({t["id"] for t in towers}) != len(towers) or any(not point_in_bounds((t["longitude"], t["latitude"]), body.bounds) for t in towers):
            raise HTTPException(422, "Duplicate tower IDs or tower outside map")
        with lock:
            if eid in experiments:
                raise HTTPException(409, "Experiment already exists; do not reset another session")
            experiments[eid] = {"id": eid, "map_id": body.map_id, "bounds": body.bounds, "towers": towers, "vehicles": {}, "incidents": {}, "delivered": {}, "sim_time": 0}
            return snapshot(experiments[eid])

    @app.put("/v1/experiments/{eid}/towers")
    def towers(eid: str, body: list[Tower]):
        with lock:
            ctx = context(eid)
            if len(body) > 32 or len({t.id for t in body}) != len(body) or any(not point_in_bounds((t.longitude, t.latitude), ctx["bounds"]) for t in body):
                raise HTTPException(422, "Invalid tower layout")
            ctx["towers"] = [t.model_dump() for t in body]
            return snapshot(ctx)

    @app.post("/v1/experiments/{eid}/tick")
    def tick(eid: str, body: Tick):
        with lock:
            ctx = context(eid)
            if body.sim_time < ctx["sim_time"] or len({v.id for v in body.vehicles}) != len(body.vehicles):
                raise HTTPException(409, "Stale simulation time or duplicate vehicle")
            if any(v.role not in ROLES or not point_in_bounds((v.longitude, v.latitude), ctx["bounds"]) for v in body.vehicles):
                raise HTTPException(422, "Invalid vehicle role or position")
            ctx["sim_time"], ctx["vehicles"] = body.sim_time, {v.id: v.model_dump() for v in body.vehicles}
            return snapshot(ctx)

    @app.post("/v1/experiments/{eid}/observations")
    def observe(eid: str, body: SensorReport):
        with lock:
            ctx = context(eid)
            if body.kind not in ("congestion", "flood", "landslide", "clear") or body.source_type not in ("synthetic_scenario", "simulated_perception"):
                raise HTTPException(422, "Unknown semantic kind/source")
            try:
                validate_geometry(body.geometry, ctx["bounds"])
                ratio, depth = body.facts.get("traffic_speed_ratio"), body.facts.get("water_depth_m")
                if body.kind == "congestion" and (type(ratio) not in (int, float) or not 0 < ratio <= 1):
                    raise ValueError("Need traffic_speed_ratio in (0,1]")
                if body.kind == "flood" and (type(depth) not in (int, float) or not 0 <= depth <= 10):
                    raise ValueError("Need water_depth_m in [0,10]")
                cells = affected_cells(body.geometry)
            except (ValueError, TypeError) as exc:
                raise HTTPException(422, str(exc)) from exc
            point = body.longitude, body.latitude
            if not point_in_bounds(point, ctx["bounds"]):
                raise HTTPException(422, "Observation outside map")
            if body.vehicle_id != "operator":
                vehicle = ctx["vehicles"].get(body.vehicle_id)
                if not vehicle or vehicle["role"] not in ("reporter", "both") or distance(point, (vehicle["longitude"], vehicle["latitude"])) > 10:
                    raise HTTPException(422, "Reporter role/telemetry does not match observation")
                if not associate(point, ctx["towers"]):
                    raise HTTPException(409, "NO_COVERAGE: buffer the report until the vehicle reconnects")
            elif body.source_type != "synthetic_scenario":
                raise HTTPException(422, "Operator injection must be labelled synthetic_scenario")
            previous = ctx["incidents"].get(body.incident_id)
            if previous is None and len(ctx["incidents"]) >= 32:
                raise HTTPException(422, "Experiment limit: 32 incident IDs, including cleared history")
            fingerprint = hashlib.sha256(json.dumps({k: v for k, v in body.model_dump().items() if k not in ("vehicle_id", "longitude", "latitude")}, sort_keys=True).encode()).hexdigest()
            if previous and body.event_version <= previous["observation"]["event_version"]:
                if body.event_version == previous["observation"]["event_version"] and fingerprint == previous["fingerprint"]:
                    reporters=previous.setdefault('reporters',[previous['reporter']])
                    if body.vehicle_id not in reporters:reporters.append(body.vehicle_id)
                    previous['assessment']=assess(body.kind,body.facts,reporters)
                    return {"accepted": True, "deduplicated": True, "incident": previous, "network": snapshot(ctx)}
                raise HTTPException(409, "Stale/conflicting incident version")
            now = datetime.now(timezone.utc)
            observation = {"experiment_id": eid, "map_id": ctx["map_id"], "event_version": body.event_version,
                           "kind": body.kind, "geometry": body.geometry, "observed_at": now.isoformat(),
                           "expires_at": (now+timedelta(seconds=body.ttl_s)).isoformat(), "source_type": body.source_type, "facts": body.facts}
            payload = {"event_id": f"alivemap:playground:{eid}:{body.incident_id}", "vehicle_id": body.vehicle_id,
                       "latitude": body.latitude, "longitude": body.longitude, "event_type": "alivemap.playground.v1:"+json.dumps(observation, separators=(",", ":")),
                       "severity": assess(body.kind,body.facts,[body.vehicle_id])['severity']}
            try:
                receipt = legacy(payload)
                expected = h3.latlng_to_cell(body.latitude, body.longitude, 10)
                if receipt.get("accepted") is not True or receipt["event"]["h3_cell"] != expected or any(receipt["event"].get(k) != v for k, v in payload.items()):
                    raise ValueError("Legacy MEC receipt disagrees with report")
            except Exception as exc:
                raise HTTPException(502, "Original MEC hazard API did not acknowledge the report") from exc
            incident = {"id": body.incident_id, "observation": observation, "h3_cells": cells, "reporter": body.vehicle_id,
                        "reporters":[body.vehicle_id],'assessment':assess(body.kind,body.facts,[body.vehicle_id]),
                        "report_tower": associate(point, ctx["towers"]), "receipt": receipt["event"], "fingerprint": fingerprint,
                        "status": "cleared" if body.kind == "clear" else "active", "received_at": utc(), "sim_time": ctx["sim_time"]}
            ctx["incidents"][body.incident_id] = incident
            return {"accepted": True, "deduplicated": False, "incident": incident, "network": snapshot(ctx)}

    @app.get("/v1/experiments/{eid}")
    def read(eid: str):
        with lock:
            return snapshot(context(eid))

    @app.delete("/v1/experiments/{eid}")
    def close(eid: str):
        with lock:
            ctx = context(eid)
            # Clear only this experiment's bridged records. Preserve all unrelated MEC data.
            for record in ctx["incidents"].values():
                payload = {k: record["receipt"][k] for k in ("event_id", "vehicle_id", "latitude", "longitude", "event_type", "severity")}
                payload.update(event_type="alivemap.playground.clear", severity=0)
                try:
                    if legacy(payload).get("accepted") is not True:
                        raise ValueError("Unacknowledged cleanup")
                except Exception as exc:
                    raise HTTPException(502, "Cleanup failed; experiment retained for retry") from exc
            if database:
                with database:
                    database.execute('DELETE FROM experiments WHERE id=?', (eid,))
            del experiments[eid]
            return {"closed": True, "experiment_id": eid}

    return app


app = create_app()
