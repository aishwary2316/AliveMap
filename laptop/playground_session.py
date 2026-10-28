"""Editable SUMO world with vehicle perception and per-vehicle MEC knowledge."""
from copy import deepcopy
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
        super().__init__(args, emit, http)
        self.used_ids.update(self.fleet)
        self.run_condition = "playground"

    def make_client(self, http):
        return PlaygroundClient(getattr(self.args, "playground_url", "http://127.0.0.1:18767"), self.run_id,
                                self.network_id, self.provider.manifest["bounds_wgs84"], self.scene["towers"], http)

    @property
    def complete(self):
        return False

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
        self.radio(f"{reporter} → MEC ACK: {anomaly['id']} {payload['kind']}; H3 r8={len(record['h3_cells']['8'])}, r10={len(record['h3_cells']['10'])}",
                   vehicle=reporter, incident=anomaly["id"], stage="acknowledged")
        return True

    def detect(self):
        acknowledged = False
        active = set(self.connection.vehicle.getIDList())
        for anomaly in self.scene["anomalies"]:
            if anomaly.get("disabled") or self.published.get(anomaly["id"], 0) >= anomaly.get("event_version", 1):
                continue
            area = self.provider.geometry_to_xy(anomaly["geometry"])
            for name in active & self.fleet.keys():
                if self.fleet[name].get("role", "both") not in ("reporter", "both"):
                    continue
                state = self.adapter.vehicle_state(name)
                key = (name, anomaly["id"], anomaly.get("event_version", 1))
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
                if self.send_observation(anomaly, name, state["lonlat"]):
                    acknowledged = True
                    break
        return acknowledged

    def step(self):
        super().step()
        self.refresh()
        if self.detect():
            self.refresh()
        else:
            self.plan()

    def edit(self, operation, payload):
        candidate = deepcopy(self.scene)
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
                # Existing vehicles retain their actual position. Placement changes use
                # a new ID, preserving truthful trajectories and SUMO insertion safety.
                if any(vehicle.get(k, 0) != self.fleet[name].get(k, 0) for k in ("origin", "position_m")):
                    raise ValueError("To relocate a vehicle, remove it and add a new ID at the desired origin")
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
        frame.update(playground=True, scene=deepcopy(self.scene), network=deepcopy(self.network), radio_events=deepcopy(self.radio_events),
                     knowledge={n: sorted(facts) for n, facts in self.knowledge.items()},
                     detected=[{"vehicle": key[0], "incident": key[1], "version": key[2]} for key in self.detected],
                     published=self.published.copy())
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
