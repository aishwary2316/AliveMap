"""A command-driven SUMO session shared by the visible lab and its tests."""
import json
from pathlib import Path
from uuid import uuid4

import traci

from .controller import mapped_hazards
from .mec_client import MecClient
from .network import SCENARIO, binary, load, match, shortest

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"cautious": "#2563eb", "standard": "#ea580c", "unaffected": "#059669", "probe": "#9333ea"}
NAMES = {"cautious": "Blue / cautious", "standard": "Orange / standard", "unaffected": "Green / unaffected", "probe": "Purple / reporting probe"}
FLEET = {
    "cautious": ("n0_2__n1_2", "n4_2__n5_2", 300),
    "standard": ("n0_2__n1_2", "n4_2__n5_2", 0),
    "unaffected": ("n0_5__n1_5", "n4_5__n5_5", 100),
}


class LiveSession:
    def __init__(self, args, emit=lambda kind, **data: None, http=None):
        self.args, self.emit = args, emit
        self.fleet = FLEET
        self.net, self.network_id = load()
        self.run_id = str(uuid4())
        self.client = MecClient(args.mec_url, self.run_id, self.network_id, http=http,
                                semantics_url=args.semantics_url)
        self.connection = None
        self.state, self.version, self.mapping = "clear", -1, []
        self.last_report_attempted = None
        self.states, self.arrived, self.decisions = {}, set(), {}
        self.applied = {}
        self.position = None
        self.output = Path(args.output) / self.run_id
        self.output.mkdir(parents=True, exist_ok=True)
        self.log_file = (self.output / "events.jsonl").open("w", encoding="utf-8")
        try:
            schema = json.loads((ROOT / "mec/baseline/openapi-observed.json").read_text())
            self.client.preflight(schema)
            self.client.snapshot()
            command = [binary("sumo-gui" if args.gui else "sumo"), "-c", str(SCENARIO / "grid.sumocfg"),
                       "--seed", "42", "--step-length", "0.5", "--no-step-log", "true",
                       "--time-to-teleport", "-1", "--collision.action", "warn",
                       "--tripinfo-output", str((self.output / "tripinfo.xml").resolve())]
            if args.gui:
                command += ["--start", "--quit-on-end", "true"]  # TraCI owns stepping; lab starts paused.
            label = "live-" + self.run_id
            traci.start(command, label=label)
            self.connection = traci.getConnection(label)
            self.baseline = {}
            for index, (vehicle, (origin, dest, risk)) in enumerate(FLEET.items()):
                route = shortest(self.net, origin, dest)
                self.baseline[vehicle] = route
                self.connection.route.add(vehicle + "-initial", route)
                self.connection.vehicle.add(vehicle, vehicle + "-initial", depart="0", departPos=str(index*25))
            route = self.baseline["cautious"]
            self.hazard_edge = route[len(route)//2]
            self.connection.route.add("probe-route", [self.hazard_edge])
            self.connection.vehicle.add("probe", "probe-route", depart="0",
                                        departPos=str(self.net.getEdge(self.hazard_edge).getLength()/2))
            self.connection.vehicle.setSpeed("probe", 0)
            self.connection.simulationStep()
            for vehicle in self.connection.vehicle.getIDList():
                color = COLORS[vehicle].lstrip("#")
                self.connection.vehicle.setColor(vehicle, tuple(int(color[i:i+2], 16) for i in (0, 2, 4)))
            x, y = self.connection.vehicle.getPosition("probe")
            lon, lat = self.net.convertXY2LonLat(x, y)
            actual, distance = match(self.net, lat, lon)
            if actual != self.hazard_edge:
                raise RuntimeError("Probe coordinate does not match its actual directed road")
            self.position = (lat, lon)
            if args.gui:
                xmin, ymin, xmax, ymax = self.net.getBoundary()
                self.connection.gui.setBoundary("View #0", xmin-60, ymin-60, xmax+60, ymax+60)
            self.record("ready", message="Connected to physical MEC. Vehicles loaded; session paused.",
                        run_id=self.run_id, hazard_edge=self.hazard_edge, match_distance_m=distance)
            self.refresh()
        except Exception:
            self.close()
            raise

    @property
    def sim_time(self):
        return self.connection.simulation.getTime()

    @property
    def complete(self):
        return self.arrived == set(self.fleet)

    def record(self, kind, **data):
        event = {"event": kind, **data}
        self.log_file.write(json.dumps(event) + "\n")
        self.log_file.flush()
        self.emit(kind, **data)

    def refresh(self):
        snapshot = self.client.snapshot()
        if snapshot["version"] != self.version:
            self.states, self.mapping = mapped_hazards(self.net, self.network_id, snapshot)
            self.state = "closed" if any(h["state"] == "closed" for h in self.states.values()) else "warning" if self.states else "clear"
            self.version = snapshot["version"]
            self.record("snapshot", sim=self.sim_time, version=self.version,
                        message=f"MEC snapshot received; semantic change #{self.version}.")
        self.plan()

    def plan(self):
        for vehicle in self.connection.vehicle.getIDList():
            if vehicle not in FLEET or self.applied.get(vehicle) == self.version:
                continue
            edge = self.connection.vehicle.getRoadID(vehicle)
            if edge.startswith(":"):
                continue
            dest, risk = FLEET[vehicle][1:]
            before = list(self.connection.vehicle.getRoute(vehicle))[self.connection.vehicle.getRouteIndex(vehicle):]
            route = shortest(self.net, edge, dest, self.states, risk)
            if route is None:
                self.connection.vehicle.setSpeed(vehicle, 0)
                explanation = "No legal route remains. Vehicle stopped."
            else:
                self.connection.vehicle.setRoute(vehicle, route)
                self.connection.vehicle.setSpeed(vehicle, -1)
                if not self.connection.vehicle.isRouteValid(vehicle):
                    raise RuntimeError("SUMO rejected the computed route")
                if any(h["state"] == "closed" for h in self.states.values()):
                    explanation = "Closure excludes the affected road; route computed from current position."
                elif self.states and risk:
                    explanation = "Warning adds a severity-weighted risk cost; vehicle chooses the cheaper route."
                elif self.states:
                    explanation = "Warning cost is zero for this vehicle; it keeps the shortest available route."
                else:
                    explanation = "Road is clear; shortest route recomputed from current position."
            self.decisions[vehicle] = explanation
            self.applied[vehicle] = self.version
            self.record("decision", sim=self.sim_time, vehicle=vehicle, before=before, after=route,
                        message=f"{NAMES[vehicle]}: {'route changed' if route and route != before else 'route retained'}. {explanation}")

    def report(self, state):
        self.last_report_attempted = state
        payload, response = self.client.report(state, *self.position)
        self.state = state
        self.record("report", sim=self.sim_time, payload=payload, response=response,
                    message=f"Physical MEC accepted {state.upper()} at t={self.sim_time:.1f}s; H3 {response['event']['h3_cell']}.")
        if state == "clear" and "probe" in self.connection.vehicle.getIDList():
            self.connection.vehicle.remove("probe")
        self.refresh()

    def step(self):
        self.connection.simulationStep()
        self.arrived.update(set(self.connection.simulation.getArrivedIDList()) & set(self.fleet))
        if self.connection.simulation.getCollidingVehiclesNumber() or self.connection.simulation.getStartingTeleportNumber():
            raise RuntimeError("Unexpected collision or teleport; paused for inspection")
        self.plan()

    def frame(self):
        vehicles = {}
        for vehicle in self.connection.vehicle.getIDList():
            if vehicle not in COLORS:
                continue
            route = list(self.connection.vehicle.getRoute(vehicle))
            index = max(0, self.connection.vehicle.getRouteIndex(vehicle))
            vehicles[vehicle] = {"position": self.connection.vehicle.getPosition(vehicle),
                                 "edge": self.connection.vehicle.getRoadID(vehicle),
                                 "speed": self.connection.vehicle.getSpeed(vehicle), "route": route[index:]}
        return {"time": self.sim_time, "state": self.state, "version": self.version,
                "run_id": self.run_id, "vehicles": vehicles, "arrived": sorted(self.arrived),
                "decisions": dict(self.decisions), "mapping": self.mapping,
                "position": self.position, "hazard_edge": self.hazard_edge,
                "complete": self.complete}

    def close(self):
        if self.client.attempted_report and self.position and (self.state != "clear" or self.last_report_attempted != "clear"):
            try:
                self.client.report("clear", *self.position)
                self.record("cleanup", message="Cleared this session's own event before closing.")
            except Exception as exc:
                self.record("cleanup_failed", message=f"Could not clear this session's event: {exc}")
        if self.connection:
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None
        self.client.close()
        self.log_file.close()
