"""Real-map scenario orchestration, sharing the existing live-session event log."""
import json
import math
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from geospatial.scenarios import observation, validate_scenario
from routing_core.agents import PROFILES, VehicleAgent
from routing_core.maps import PackageMapProvider, read_json
from .geo_mec import GeoMecClient
from .live_session import COLORS, LiveSession, ROOT
from .sumo_adapter import SumoAdapter


class GeoSession(LiveSession):
    def __init__(self, args, emit=lambda kind, **data: None, http=None):
        self.args, self.emit = args, emit
        prepared = getattr(args, '_prepared_provider', None)
        self.provider = prepared if prepared and prepared.path == Path(args.map_package).resolve() else PackageMapProvider(args.map_package)
        args._prepared_provider = None
        self.scenario = read_json(getattr(args, "scenario", None) or self.provider.path/self.provider.manifest["scenario"])
        if getattr(args, "playground_scene", None) is not None:
            from routing_core.playground import validate_scene
            self.scene = validate_scene(self.provider, args.playground_scene)
            self.scenario = deepcopy(self.scenario)
            self.scenario["vehicles"], self.scenario["events"] = self.scene["vehicles"], []
        validate_scenario(self.provider, self.scenario)
        self.scenario = deepcopy(self.scenario)
        self.incident_kind = getattr(args, "incident_kind", None)
        self.run_condition, self.reported_kinds = self.incident_kind or "legacy", set()
        if self.incident_kind is not None:
            if self.incident_kind not in ("none", "congestion", "flood", "landslide"):
                raise ValueError("Unknown incident selection")
            # Comparison runs hold the selected incident until explicit clearance.
            self.scenario["events"] = [] if self.incident_kind == "none" else [
                {"sim_time_s": float(getattr(args, "incident_at", 20)), "kind": self.incident_kind}]
        self.fleet = self.scenario["vehicles"]
        self.run_id = str(uuid4())
        self.network_id = self.provider.manifest["map_id"]
        self.client = self.make_client(http)
        self.output = Path(args.output)/self.run_id
        self.output.mkdir(parents=True, exist_ok=True)
        self.log_file = (self.output/"events.jsonl").open("w", encoding="utf-8")
        self.adapter, self.connection = SumoAdapter(), None
        self.state, self.version, self.mapping = "clear", -1, []
        self.applied, self.decisions, self.arrived = {}, {}, set()
        self.facts, self.baseline, self.event_version = [], {}, 0
        self.route_history, self.planned_routes, self.driven_edges = {}, {}, {name: [] for name in self.fleet}
        self.reroute_counts, self.blocked, self.arrival_times = {name: 0 for name in self.fleet}, set(), {}
        self.hazard_edge = self.scenario["hazard"]["anchor_edge"]
        self.position = None
        self.agents = {name: VehicleAgent(self.provider, PROFILES[vehicle["profile"]]) for name, vehicle in self.fleet.items()}
        try:
            self.client.preflight(read_json(ROOT/"mec/baseline/openapi-observed.json"))
            self.client.facts()
            self.adapter.load_map(self.provider, self.output, self.run_id, args.gui)
            self.connection = self.adapter.connection
            for name, vehicle in self.fleet.items():
                route, _ = self.agents[name].route(vehicle["origin"], vehicle["destination"])
                if route is None:
                    raise ValueError("No feasible initial route")
                self.baseline[name] = route
                self.planned_routes[name] = list(route)
                self.route_history[name] = []
                from .map_canvas import color_for
                color = color_for(name).lstrip("#")
                self.adapter.spawn(name, route, tuple(int(color[i:i+2], 16) for i in (0, 2, 4)), position=vehicle.get("position_m", 0))
            self.adapter.step()
            if args.gui and self.baseline:
                points = [point for route in self.baseline.values() for eid in route for point in self.provider.edges[eid]["shape_xy"]]
                xs, ys = zip(*points)
                self.connection.gui.setBoundary("View #0", min(xs)-100, min(ys)-100, max(xs)+100, max(ys)+100)
                self.connection.gui.setSchema("View #0", "real world")
            self.record("ready", message="Real map loaded; paused. Semantic incidents are synthetic.", run_id=self.run_id,
                        map_id=self.network_id, build_id=self.provider.manifest["build_id"], scenario_id=self.scenario["scenario_id"],
                        baseline=self.baseline, label=self.scenario["label"])
            self.refresh()
        except Exception:
            self.close()
            raise

    def make_client(self, http):
        return GeoMecClient(self.args.mec_url, self.run_id, self.network_id, http=http, semantics_url=self.args.semantics_url)

    def refresh(self):
        snapshot = self.client.facts()
        if snapshot["version"] != self.version:
            self.version, self.facts = snapshot["version"], snapshot["facts"]
            self.state = self.facts[-1].kind if self.facts else "clear"
            self.mapping = [{"kind": fact.kind, "edges": self.provider.edges_intersecting_geometry(fact.geometry)} for fact in self.facts]
            if self.args.gui:
                for pid in list(self.connection.polygon.getIDList()):
                    if pid.startswith("incident-"):
                        self.connection.polygon.remove(pid)
                for i, fact in enumerate(self.facts):
                    geometry = self.provider.geometry_to_xy(fact.geometry)
                    parts = [geometry] if geometry.geom_type == "Polygon" else geometry.geoms
                    for j, polygon in enumerate(parts):
                        self.connection.polygon.add(f"incident-{i}-{j}", list(polygon.exterior.coords), (230, 30, 30, 160), fill=True, layer=101)
            self.record("snapshot", sim=self.sim_time, version=self.version, mapping=self.mapping,
                        message=f"MEC semantic update {self.version}: {self.state}")
        self.plan()

    def plan(self):
        for name in self.connection.vehicle.getIDList():
            if name not in self.fleet or self.applied.get(name) == self.version:
                continue
            state = self.adapter.vehicle_state(name)
            if state["edge"].startswith(":"):
                continue
            xy = self.provider.lonlat_to_xy(*state["lonlat"])
            if math.dist(xy, state["position"]) > 0.05:
                raise ValueError("TraCI/map geographic conversion differs by more than 5 cm")
            route, cost = self.agents[name].route(state["edge"], self.fleet[name]["destination"], self.facts)
            changed = route != state["route"]
            if self.version > 0 and changed:
                self.route_history[name].append({"sim_time": self.sim_time, "version": self.version, "reason": self.state,
                                                 "old": list(self.planned_routes[name]), "new": None if route is None else list(route)})
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
            if self.args.gui:
                pid = "computed-route-"+name
                if pid in self.connection.polygon.getIDList():
                    self.connection.polygon.remove(pid)
                if route:
                    points = [xy for eid in route for xy in self.provider.edges[eid]["shape_xy"]]
                    color = COLORS[name].lstrip("#")
                    rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
                    self.connection.polygon.add(pid, points, rgb+(200,), fill=False, layer=100, lineWidth=5)
            self.applied[name] = self.version
            message = f"{name}: no feasible route; stopped" if route is None else f"{name}: {self.fleet[name]['profile']}; {'route changed' if route != state['route'] else 'route retained'}"
            self.decisions[name] = message
            self.record("decision", vehicle=name, sim=self.sim_time, before=state["route"], after=route,
                        cost=None if route is None else cost, message=message)

    def report(self, kind):
        kind = {"warning": self.incident_kind if self.incident_kind not in (None, "none") else self.scenario["hazard"]["kind"], "closed": "landslide"}.get(kind, kind)
        if kind != "clear":
            self.reported_kinds.add(kind)
            if self.incident_kind is not None:
                self.run_condition = ("mixed:"+"+".join(sorted(self.reported_kinds)) if len(self.reported_kinds) > 1 else
                                      kind if kind == self.incident_kind else "manual:"+kind)
        self.event_version += 1
        fact = observation(self.provider, self.scenario, self.run_id, self.event_version, kind)
        payload, response = self.client.report_fact(fact)
        self.record("report", sim=self.sim_time, payload=payload, response=response,
                    message=f"MEC accepted {kind}; H3 {response['event']['h3_cell']}")
        self.state = kind
        self.refresh()

    def step(self):
        for name in self.connection.vehicle.getIDList():
            if name in self.fleet:
                edge = self.connection.vehicle.getRoadID(name)
                if not edge.startswith(":") and (not self.driven_edges[name] or self.driven_edges[name][-1] != edge):
                    self.driven_edges[name].append(edge)
        self.adapter.step()
        newly_arrived = set(self.connection.simulation.getArrivedIDList()) & set(self.fleet)
        self.arrived.update(newly_arrived)
        self.arrival_times.update({name: self.sim_time for name in newly_arrived})
        self.plan()

    def frame(self):
        vehicles = {name: self.adapter.vehicle_state(name) for name in self.connection.vehicle.getIDList() if name in self.fleet}
        for name in self.blocked & vehicles.keys():
            vehicles[name]["route"] = []  # A stopped vehicle has no currently feasible intended route.
            vehicles[name]["blocked"] = True
        return {"time": self.sim_time, "state": self.state, "version": self.version, "run_id": self.run_id,
                "map_id": self.network_id, "scenario_id": self.scenario["scenario_id"], "vehicles": vehicles,
                "arrived": sorted(self.arrived), "decisions": self.decisions.copy(), "mapping": self.mapping,
                "position": None, "hazard_edge": self.hazard_edge, "complete": self.complete,
                "vehicle_status": {name: "arrived" if name in self.arrived else "active" if name in vehicles else "queued" for name in self.fleet},
                "facts": [{"kind": fact.kind, "geometry": fact.geometry} for fact in self.facts],
                "baseline_routes": self.baseline, "planned_routes": {name: list(route) for name, route in self.planned_routes.items()},
                "route_history": deepcopy(self.route_history), "reroute_counts": self.reroute_counts.copy(),
                "blocked": sorted(self.blocked), "driven_edges": {name: list(route) for name, route in self.driven_edges.items()}, "arrival_times": self.arrival_times.copy(),
                "incident_kind": self.incident_kind, "comparison_condition": self.run_condition,
                "incident_schedule": self.scenario["events"]}

    def close(self):
        if self.client.attempted_report and self.state != "clear":
            try:
                self.event_version += 1
                self.client.report_fact(observation(self.provider, self.scenario, self.run_id, self.event_version, "clear"))
            except Exception as exc:
                self.record("cleanup_failed", message=str(exc))
        try:
            self.adapter.close()
        finally:
            self.connection = None
            self.client.close()
            self.log_file.close()


class ScenarioController:
    """Activation owns epochs and adapter lifetime, never vehicle route selection."""
    def __init__(self, args, emit=lambda kind, **data: None, http_factory=None):
        self.args, self.emit, self.http_factory = args, emit, http_factory
        self.session = None

    def activate(self, package, scenario=None):
        # Validate before replacing the old session. Activation failures remain errors.
        provider = PackageMapProvider(package)
        validate_scenario(provider, read_json(scenario or provider.path/provider.manifest["scenario"]))
        self.close()
        self.args.map_package, self.args.scenario = str(package), scenario
        self.session = GeoSession(self.args, self.emit, self.http_factory() if self.http_factory else None)
        return self.session

    def command(self, epoch, action, value=None):
        if not self.session or epoch != self.session.run_id:
            return False
        if action == "report":
            self.session.report(value)
        elif action == "step":
            self.session.step()
        else:
            raise ValueError("Unknown scenario command")
        return True

    def close(self):
        if self.session:
            self.session.close()
            self.session = None
