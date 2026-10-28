"""SUMO execution only: the routing core never imports this module."""
from typing import Protocol

import traci

from .network import binary


class SimulatorAdapter(Protocol):
    def load_map(self, provider, output, epoch, gui=False): ...
    def step(self) -> float: ...
    def vehicle_state(self, vehicle_id) -> dict: ...
    def apply_route(self, vehicle_id, edge_ids): ...
    def close(self): ...


class SumoAdapter:
    def __init__(self):
        self.connection = None

    def load_map(self, provider, output, epoch, gui=False):
        self.provider = provider
        command = [binary("sumo-gui" if gui else "sumo"), "-c", str(provider.path/provider.manifest["sumo_config"]),
                   "--seed", "42", "--step-length", "0.5", "--no-step-log", "true", "--time-to-teleport", "-1",
                   "--tripinfo-output", str((output/"tripinfo.xml").resolve())]
        if gui:
            command += ["--start", "--quit-on-end", "true", "--window-size", "1200,800", "--window-pos", "20,20"]
        traci.start(command, label=epoch)
        self.connection = traci.getConnection(epoch)

    def spawn(self, vehicle, route, color):
        self.provider.validate_route(route)
        self.connection.route.add(vehicle+"-initial", route)
        self.connection.vehicle.add(vehicle, vehicle+"-initial", depart="0", departPos="base", departSpeed="0")
        self.connection.vehicle.setColor(vehicle, color)

    def step(self):
        self.connection.simulationStep()
        if self.connection.simulation.getCollidingVehiclesNumber() or self.connection.simulation.getStartingTeleportNumber():
            raise RuntimeError("Unexpected collision or teleport")
        return self.connection.simulation.getTime()

    def vehicle_state(self, vehicle_id):
        vehicle = self.connection.vehicle
        xy = vehicle.getPosition(vehicle_id)
        lonlat = self.connection.simulation.convertGeo(*xy)
        return {"position": xy, "lonlat": lonlat, "edge": vehicle.getRoadID(vehicle_id), "speed": vehicle.getSpeed(vehicle_id),
                "angle": vehicle.getAngle(vehicle_id),
                "route": list(vehicle.getRoute(vehicle_id))[max(0, vehicle.getRouteIndex(vehicle_id)):]}

    def apply_route(self, vehicle_id, edge_ids):
        if edge_ids is None:
            self.connection.vehicle.setSpeed(vehicle_id, 0)
            return
        self.provider.validate_route(edge_ids)
        self.connection.vehicle.setRoute(vehicle_id, edge_ids)
        self.connection.vehicle.setSpeed(vehicle_id, -1)
        if not self.connection.vehicle.isRouteValid(vehicle_id):
            raise RuntimeError("SUMO rejected the independently computed route")

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None
