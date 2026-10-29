"""Editable SUMO world with vehicle perception and per-vehicle MEC knowledge."""
from copy import deepcopy
import time
from datetime import datetime, timedelta, timezone

from shapely.geometry import Point

from routing_core.agents import Observation, VehicleAgent, PROFILES
from routing_core.playground import validate_scene
from .geo_session import GeoSession
from .playground_client import PlaygroundClient
from .map_canvas import color_for


class PlaygroundSession(GeoSession):
    def __init__(self, args, emit=lambda kind, **data: None, http=None):
        self.knowledge, self.seen, self.detected, self.published = {}, {}, {}, {}
        self.network, self.radio_events, self.used_ids = {}, [], set()
        self.handles_network_poll = True
        self.last_network_wall = 0
        self.last_upload_tick = {}
        self.reported=set()
        self.operator_versions=set()
        self._sensor_areas = {}
        super().__init__(args, emit, http)
        self.used_ids.update(self.fleet)
        self.run_condition = (self.scene['anomalies'][0]['kind'] if self.scene['anomalies'] else 'none') if self.scene.get('story') else 'playground'

    def make_client(self, http):
        return PlaygroundClient(getattr(self.args, "playground_url", "http://127.0.0.1:18767"), self.run_id,
                                self.network_id, self.provider.manifest["bounds_wgs84"], self.scene["towers"], http)

    @property
    def complete(self):
        if not getattr(self,'scene',{}).get('story'):return False
        followers={name for name,v in self.fleet.items() if v.get('role')=='receiver'}
        reported={key[0] for key in self.reported}
        corroborated=not self.scene['anomalies'] or {'scout-1','scout-2'}.issubset(reported)
        return bool(followers) and followers.issubset(self.arrived|self.blocked) and corroborated

    def radio(self, message, **data):
        record = {"sim_time": self.sim_time, "message": message, **data}
        self.radio_events.append(record)
        self.radio_events = self.radio_events[-80:]
        self.record("radio", sim=self.sim_time, **data, message=message)

    def refresh(self):
        telemetry = []
        for name in self.connection.vehicle.getIDList():
            if name in self.fleet:
                ll = self.adapter.vehicle_state(name)["lonlat"]
                telemetry.append({"id": name, "longitude": ll[0], "latitude": ll[1], "role": self.fleet[name].get("role", "both")})
        previous = self.network
        self.network = self.client.tick(self.sim_time, telemetry)
        self.last_network_wall = time.monotonic()
        for record in self.network["incidents"]:
            self.published[record["id"]] = max(self.published.get(record["id"], 0), record["observation"]["event_version"])
        for name, association in self.network["associations"].items():
            old = previous.get("associations", {}).get(name, {}).get("tower_id")
            if old != association["tower_id"]:
                self.radio(f"{name}: serving tower {association['tower_id'] or 'NO COVERAGE'}", vehicle=name)
        for name in self.fleet:
            known = self.knowledge.setdefault(name, {})
            for record in self.network["deliveries"].get(name, []):
                fact = Observation(**record["observation"]).validate()
                key = (name, record["id"])
                stamp = (fact.event_version, record["status"])
                if self.seen.get(key) != stamp:
                    self.radio(f"MEC → {name}: {record['id']} v{fact.event_version} ({record['status']})", vehicle=name, incident=record["id"])
                    self.seen[key] = stamp
                if record["status"] == "active" and fact.active():
                    known[record["id"]] = fact
                else:
                    known.pop(record["id"], None)
            self.knowledge[name] = {key: fact for key, fact in known.items() if fact.active()}
        records = [r for r in self.network["incidents"] if r["status"] == "active"]
        self.facts = [Observation(**r["observation"]) for r in records]
        self.version = sum(r["observation"]["event_version"] for r in self.network["incidents"])
        self.state = "+".join(sorted({f.kind for f in self.facts})) or "clear"
        self.mapping = [{"id": r["id"], "kind": r["observation"]["kind"], "h3_cells": r["h3_cells"],
                         "edges": self.provider.edges_intersecting_geometry(r["observation"]["geometry"])} for r in records]
        self.plan()

    def plan(self):
        for name in self.connection.vehicle.getIDList():
            if name not in self.fleet:
                continue
            facts = self.knowledge.get(name, {})
            signature = (self.fleet[name]["profile"], self.fleet[name]["destination"],
                         tuple(sorted((key, f.event_version, f.kind) for key, f in facts.items())))
            if self.applied.get(name) == signature:
                continue
            state = self.adapter.vehicle_state(name)
            if state["edge"].startswith(":"):
                continue
            route, cost = self.agents[name].route(state["edge"], self.fleet[name]["destination"], facts.values())
            changed = route != state["route"]
            was_blocked = name in self.blocked
            if changed and (facts or name in self.applied or was_blocked):
                self.route_history[name].append({"sim_time": self.sim_time, "version": self.version,
                                                "reason": ", ".join(facts) or "clearance / profile update",
                                                "old": list(state["route"]), "new": None if route is None else list(route)})
                if route is not None:
                    self.reroute_counts[name] += 1
            if route is None:
                self.blocked.add(name)
            else:
                self.blocked.discard(name)
                prefix = list(self.driven_edges[name])
                if prefix and prefix[-1] == route[0]:
                    prefix.pop()
                self.planned_routes[name] = prefix+list(route)
            self.adapter.apply_route(name, route)
            self.applied[name] = signature
            self.decisions[name] = ("No feasible route; stopped" if route is None else "Route changed" if changed else "Route retained")+f"; {len(facts)} known incident(s)"
            self.record("decision", vehicle=name, sim=self.sim_time, before=state["route"], after=route,
                        cost=cost if route else None, message=name+": "+self.decisions[name])

    def payload(self, anomaly, reporter, ll, kind=None):
        kind = kind or anomaly["kind"]
        facts = {"traffic_speed_ratio": anomaly.get("traffic_speed_ratio", .08)} if kind == "congestion" else {
            "water_depth_m": anomaly.get("water_depth_m", .25)} if kind == "flood" else {}
        return {"incident_id": anomaly["id"], "vehicle_id": reporter, "longitude": ll[0], "latitude": ll[1],
                "kind": kind, "geometry": anomaly["geometry"], "facts": facts,
                "event_version": anomaly.get("event_version", 1), "ttl_s": anomaly.get("ttl_s", 1800),
                "source_type": "synthetic_scenario" if reporter == "operator" else "simulated_perception"}

    def send_observation(self, anomaly, reporter, ll, kind=None):
        payload = self.payload(anomaly, reporter, ll, kind)
        response = self.client.observe(payload)
        if response is None:
            return False
        self.published[anomaly["id"]] = payload["event_version"]
        record = response["incident"]
        assessment=record.get('assessment',{})
        self.radio(f"{reporter} → MEC ACK: {anomaly['id']} {payload['kind']}; H3 r8={len(record['h3_cells']['8'])}, r10={len(record['h3_cells']['10'])}",
                   vehicle=reporter, incident=anomaly["id"], stage="acknowledged")
        if assessment:self.radio(f"MEC assessed {anomaly['id']}: severity {assessment['severity']}, priority {assessment['priority']}, {assessment['independent_reporters']} reporter(s), {assessment['confidence']}",incident=anomaly['id'],stage='assessed')
        return True

    def detect(self):
        acknowledged = False
        active = set(self.connection.vehicle.getIDList())
        for anomaly in self.scene["anomalies"]:
            if anomaly.get("disabled"):
                continue
            if (anomaly['id'],anomaly.get('event_version',1)) in self.operator_versions:continue
            stamp = anomaly.get('event_version',1)
            cached = self._sensor_areas.get(anomaly['id'])
            if not cached or cached[0] != stamp:
                cached = (stamp,self.provider.geometry_to_xy(anomaly['geometry']))
                self._sensor_areas[anomaly['id']] = cached
            area = cached[1]
            for name in active & self.fleet.keys():
                if self.fleet[name].get("role", "both") not in ("reporter", "both"):
                    continue
                state = self.adapter.vehicle_state(name)
                key = (name, anomaly["id"], anomaly.get("event_version", 1))
                if key in self.reported:continue
                if key not in self.detected:
                    # A synthetic sensor sees the area within a bounded local radius.
                    if area.distance(Point(*state["position"])) > anomaly.get("detect_m", 20):
                        continue
                    now = datetime.now(timezone.utc)
                    payload = self.payload(anomaly, name, state["lonlat"])
                    fact = Observation(self.run_id, self.network_id, payload["event_version"], anomaly["kind"], anomaly["geometry"],
                                       now.isoformat(), (now+timedelta(seconds=anomaly.get("ttl_s", 1800))).isoformat(), "simulated_perception", payload["facts"])
                    self.knowledge.setdefault(name, {})[anomaly["id"]] = fact
                    self.detected[key] = True
                    self.radio(f"{name}: detected {anomaly['id']}; upload queued until coverage", vehicle=name, incident=anomaly["id"], stage="detected")
                # Outside coverage a buffered report retries only after new
                # telemetry. A new observation always gets exact current
                # telemetry before upload; no stale-position shortcuts.
                tick = self.network.get('sim_time', -1)
                if self.last_upload_tick.get(key) == tick:
                    continue
                association = self.network.get('associations', {}).get(name, {})
                if not association.get('tower_id'):
                    continue
                if tick != self.sim_time:
                    self.refresh()
                self.last_upload_tick[key] = self.sim_time
                if self.send_observation(anomaly, name, state["lonlat"]):
                    self.reported.add(key)
                    acknowledged = True
                    break
        return acknowledged

    def radio_boundary_crossed(self):
        # A cheap local prediction triggers immediate telemetry at coverage
        # boundaries. Only the server's response authorizes upload/delivery.
        from mec.playground_api import distance
        active = set(self.connection.vehicle.getIDList()) & self.fleet.keys()
        if active != set(self.network.get('associations', {})):
            return True
        for name in active:
            if self.fleet[name].get('role', 'both') == 'offline':
                continue  # MEC deliberately leaves offline vehicles unassociated.
            ll = self.adapter.vehicle_state(name)['lonlat']
            candidates = [(distance(ll, (t['longitude'],t['latitude'])),t['id'],t['radius_m']) for t in self.scene['towers']]
            nearest = min(((d,tid) for d,tid,r in candidates if d<=r),default=(0,None))[1]
            if nearest != self.network.get('associations',{}).get(name,{}).get('tower_id'):
                return True
        return False

    def step(self):
        super().step()
        # Physical HTTPS is paced by wall time, not a blocking round trip per
        # 0.5 simulated seconds. Perception still runs at every SUMO step.
        # Local mode preserves step-by-step deterministic delivery for tests.
        if self.mec_mode_local or time.monotonic()-self.last_network_wall >= .25 or self.radio_boundary_crossed():
            self.refresh()
        if self.detect():
            self.refresh()
        else:
            self.plan()

    @property
    def mec_mode_local(self):
        return getattr(self.args, 'mec_mode', 'physical') == 'local'

    def edit(self, operation, payload):
        candidate = deepcopy(self.scene)
        candidate.pop('story',None)
        name = payload.get("id")
        if operation in ("vehicle", "remove_vehicle"):
            if operation == "remove_vehicle":
                candidate["vehicles"].pop(name)
            else:
                candidate["vehicles"][name] = {k: v for k, v in payload.items() if k != "id"}
        elif operation in ("tower", "remove_tower", "anomaly", "remove_anomaly"):
            key = "towers" if "tower" in operation else "anomalies"
            candidate[key] = [v for v in candidate[key] if v["id"] != name]
            if not operation.startswith("remove"):
                item = deepcopy(payload)
                if key == "anomalies":
                    item["event_version"] = max(self.published.get(name, 0), next((a.get("event_version", 1) for a in self.scene[key] if a["id"] == name), 0))+1
                candidate[key].append(item)
        elif operation in ("publish", "clear"):
            anomaly = next(a for a in self.scene["anomalies"] if a["id"] == name)
            if operation == "clear":
                anomaly["event_version"] = max(anomaly.get("event_version", 1), self.published.get(name, 0))+1
            centroid = self.provider.geometry_to_xy(anomaly["geometry"]).centroid
            self.send_observation(anomaly, "operator", self.provider.xy_to_lonlat(centroid.x, centroid.y), "clear" if operation == "clear" else None)
            self.operator_versions.add((name,anomaly.get('event_version',1)))
            self.scene.pop('story',None);self.run_condition='playground'
            if operation == "clear":
                anomaly["disabled"] = True
            self.refresh()
            return
        else:
            raise ValueError("Unknown playground operation")
        candidate = validate_scene(self.provider, candidate)
        if operation == "remove_anomaly" and name in self.published:
            self.edit("clear", {"id": name})
        if operation == "vehicle":
            vehicle = candidate["vehicles"][name]
            if name in self.fleet:
                if any(vehicle.get(k, 0) != self.fleet[name].get(k, 0) for k in ("origin", "position_m")):
                    route,_=VehicleAgent(self.provider,PROFILES[vehicle['profile']]).route(vehicle['origin'],vehicle['destination'])
                    rgb=color_for(name).lstrip('#')
                    self.adapter.relocate(name,route,vehicle.get('position_m',0),tuple(int(rgb[i:i+2],16) for i in (0,2,4)))
                    self.baseline[name]=route;self.planned_routes[name]=list(route);self.driven_edges[name]=[]
                    self.route_history[name]=[];self.reroute_counts[name]=0;self.blocked.discard(name)
                    self.applied.pop(name,None)
                    self.radio(f'{name}: operator relocated vehicle to {vehicle["origin"]}; a new driving segment starts here',vehicle=name,stage='manual_placement')
                current = self.adapter.vehicle_state(name)["edge"] if name in self.connection.vehicle.getIDList() else vehicle["origin"]
                if not current.startswith(":") and VehicleAgent(self.provider, PROFILES[vehicle["profile"]]).route(current, vehicle["destination"])[0] is None:
                    raise ValueError("Destination is unreachable from the vehicle's current directed road")
            elif name in self.used_ids:
                raise ValueError("Choose a new vehicle ID; IDs are not reused within a SUMO run")
            else:
                agent = VehicleAgent(self.provider, PROFILES[vehicle["profile"]])
                route, _ = agent.route(vehicle["origin"], vehicle["destination"])
                rgb = color_for(name).lstrip("#")
                self.adapter.spawn(name, route, tuple(int(rgb[i:i+2], 16) for i in (0, 2, 4)), vehicle.get("position_m", 0))
                self.baseline[name], self.planned_routes[name], self.driven_edges[name], self.route_history[name] = route, route, [], []
                self.reroute_counts[name] = 0
                self.used_ids.add(name)
            self.agents[name] = VehicleAgent(self.provider, PROFILES[vehicle["profile"]])
            if vehicle.get("role") == "offline":
                self.knowledge[name] = {}
        elif operation == "remove_vehicle":
            if name in self.connection.vehicle.getIDList():
                self.connection.vehicle.remove(name)
            elif name in self.connection.simulation.getPendingVehicles():
                self.connection.vehicle.remove(name)
            for store in (self.agents, self.knowledge, self.applied, self.baseline, self.planned_routes, self.driven_edges, self.route_history, self.reroute_counts, self.decisions, self.arrival_times):
                store.pop(name, None)
            self.arrived.discard(name); self.blocked.discard(name)
        if "tower" in operation:
            self.client.set_towers(candidate["towers"])
        self.scene = candidate
        self.run_condition='playground'
        self.fleet = self.scenario["vehicles"] = self.scene["vehicles"]
        self.refresh()

    def export_scene(self):
        scene = deepcopy(self.scene)
        for a in scene["anomalies"]:
            a.pop("event_version", None)
            a.pop("disabled", None)
        return scene

    def report(self, kind):
        raise ValueError("Select an anomaly in Playground, then Publish or Clear selected")

    def frame(self):
        frame = super().frame()
        frame.update(playground=True, mec_endpoint=self.client.endpoint_url, scene=deepcopy(self.scene), network=deepcopy(self.network), radio_events=deepcopy(self.radio_events),
                     knowledge={n: sorted(facts) for n, facts in self.knowledge.items()},
                     detected=[{"vehicle": key[0], "incident": key[1], "version": key[2]} for key in self.detected],
                     published=self.published.copy())
        if self.scene.get('story'):
            records=self.network.get('incidents',[])
            reports=max((len(r.get('reporters',[r['reporter']])) for r in records),default=0)
            changes=sum(self.reroute_counts.values())
            frame['narration']=('Baseline: identical vehicles and trips, no anomaly. Compare routes and arrival times.' if not self.scene['anomalies'] else
                '1 · Scouts are sensing independently. No MEC incident has been received yet.' if not reports else
                f'2 · First scout reported. MEC computed affected H3 cells and risk; waiting for independent corroboration. Route changes: {changes}.' if reports==1 else
                f'3 · {reports} independent scouts reported. MEC corroborated the incident and delivered through simulated tower coverage. Actual route changes: {changes}. Solid=current, dashed=previous.')
            if self.complete:frame['narration']='4 · Story finished: followers arrived or stopped safely. Compare the baseline, replay, or edit the scene.'
            if self.blocked:frame['narration']+=' No feasible route: '+', '.join(sorted(self.blocked))+' stopped safely.'
        return frame

    def close(self):
        try:
            if hasattr(self, "adapter"):
                self.adapter.close()
        finally:
            self.connection = None
            try:
                self.client.close()
            finally:
                if hasattr(self, "log_file"):
                    self.log_file.close()
