"""Real-map scenario orchestration, sharing the existing live-session event log."""
import json
import math
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
        self.provider = PackageMapProvider(args.map_package)
        self.scenario = read_json(getattr(args, "scenario", None) or self.provider.path/self.provider.manifest["scenario"])
        validate_scenario(self.provider, self.scenario)
        self.fleet = self.scenario["vehicles"]
        self.run_id = str(uuid4())
        self.network_id = self.provider.manifest["map_id"]
        self.client = GeoMecClient(args.mec_url, self.run_id, self.network_id, http=http, semantics_url=args.semantics_url)
        self.output = Path(args.output)/self.run_id
        self.output.mkdir(parents=True, exist_ok=True)
        self.log_file = (self.output/"events.jsonl").open("w", encoding="utf-8")
        self.adapter, self.connection = SumoAdapter(), None
        self.state, self.version, self.mapping = "clear", -1, []
        self.applied, self.decisions, self.arrived = {}, {}, set()
        self.facts, self.baseline, self.event_version = [], {}, 0
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
                color = COLORS[name].lstrip("#")
                self.adapter.spawn(name, route, tuple(int(color[i:i+2], 16) for i in (0, 2, 4)))
            self.adapter.step()
            if args.gui:
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
        kind = {"warning": self.scenario["hazard"]["kind"], "closed": "landslide"}.get(kind, kind)
        self.event_version += 1
        fact = observation(self.provider, self.scenario, self.run_id, self.event_version, kind)
        payload, response = self.client.report_fact(fact)
        self.record("report", sim=self.sim_time, payload=payload, response=response,
                    message=f"MEC accepted {kind}; H3 {response['event']['h3_cell']}")
        self.state = kind
        self.refresh()

    def step(self):
        self.adapter.step()
        self.arrived.update(set(self.connection.simulation.getArrivedIDList()) & set(self.fleet))
        self.plan()

    def frame(self):
        vehicles = {name: self.adapter.vehicle_state(name) for name in self.connection.vehicle.getIDList() if name in self.fleet}
        return {"time": self.sim_time, "state": self.state, "version": self.version, "run_id": self.run_id,
                "map_id": self.network_id, "scenario_id": self.scenario["scenario_id"], "vehicles": vehicles,
                "arrived": sorted(self.arrived), "decisions": self.decisions.copy(), "mapping": self.mapping,
                "position": None, "hazard_edge": self.hazard_edge, "complete": self.complete}

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
