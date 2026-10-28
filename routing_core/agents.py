"""Vehicle-side A* and semantic facts. This module imports no simulator APIs."""
import heapq
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from shapely.geometry import shape


@dataclass(frozen=True)
class VehicleProfile:
    name: str
    congestion_weight: float = 1.0
    max_water_depth_m: float = 0.2
    water_risk_s_per_m: float = 50.0
    uphill_s_per_m: float = 0.0
    max_grade: float = 0.25
    vehicle_class: str = "passenger"


PROFILES = {
    "time_sensitive": VehicleProfile("time_sensitive", congestion_weight=3.0, max_water_depth_m=0.15, uphill_s_per_m=0.1),
    "distance_focused": VehicleProfile("distance_focused", congestion_weight=0.03, max_water_depth_m=0.5, water_risk_s_per_m=5),
    "low_clearance": VehicleProfile("low_clearance", max_water_depth_m=0.15, uphill_s_per_m=0.2),
    "high_clearance": VehicleProfile("high_clearance", max_water_depth_m=0.5, water_risk_s_per_m=5, uphill_s_per_m=0.05),
}


@dataclass
class Observation:
    experiment_id: str
    map_id: str
    event_version: int
    kind: str
    geometry: dict
    observed_at: str
    expires_at: str
    source_type: str = "synthetic_scenario"
    facts: dict[str, Any] = field(default_factory=dict)

    def validate(self):
        if not self.experiment_id or not self.map_id or type(self.event_version) is not int or self.event_version < 1:
            raise ValueError("Invalid observation identity/version")
        if self.kind not in ("congestion", "flood", "landslide", "clear"):
            raise ValueError("Unknown semantic observation kind")
        if self.source_type not in ("synthetic_scenario", "simulated_perception", "actual_sensor"):
            raise ValueError("Unknown observation source")
        geometry = shape(self.geometry)
        if geometry.is_empty or not geometry.is_valid or geometry.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError("Semantic hazard requires a valid geographic area")
        west, south, east, north = geometry.bounds
        if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
            raise ValueError("Invalid geographic hazard bounds")
        observed, expires = datetime.fromisoformat(self.observed_at), datetime.fromisoformat(self.expires_at)
        if observed.tzinfo is None or expires.tzinfo is None or expires <= observed:
            raise ValueError("Observation timestamps must be aware and expiry must follow observation")
        if self.kind == "flood" and (type(self.facts.get("water_depth_m")) not in (int, float) or not 0 <= self.facts["water_depth_m"] <= 10):
            raise ValueError("Flood observation needs bounded water depth")
        if self.kind == "congestion" and (type(self.facts.get("traffic_speed_ratio")) not in (int, float) or not 0 < self.facts.get("traffic_speed_ratio", 0) <= 1):
            raise ValueError("Congestion observation needs a speed ratio in (0,1]")
        return self

    def active(self, now=None):
        self.validate()
        return self.kind != "clear" and datetime.fromisoformat(self.expires_at) > (now or datetime.now(timezone.utc))


class VehicleAgent:
    def __init__(self, provider, profile):
        self.map = provider
        self.profile = profile

    def route(self, start, destination, observations=(), heuristic=True):
        if start not in self.map.edges or destination not in self.map.edges:
            raise ValueError("Unknown start/destination road")
        affected = {}
        for observation in observations:
            if observation.map_id != self.map.manifest["map_id"]:
                raise ValueError("Observation belongs to a different map")
            if observation.active():
                for eid in self.map.edges_intersecting_geometry(observation.geometry, self.profile.vehicle_class):
                    affected.setdefault(eid, []).append(observation)
        target = self.map.edges[destination]["shape_xy"][-1]

        def estimate(eid):
            point = self.map.edges[eid]["shape_xy"][-1]
            return math.dist(point, target)/self.map.max_speed if heuristic else 0

        costs, parents = {start: 0.0}, {}
        queue = [(estimate(start), 0.0, start)]
        while queue:
            _, cost, eid = heapq.heappop(queue)
            if cost != costs[eid]:
                continue
            if eid == destination:
                route = [eid]
                while route[-1] != start:
                    route.append(parents[route[-1]])
                route.reverse()
                self.map.validate_route(route, self.profile.vehicle_class)
                return route, cost
            for nxt in self.map.neighbors(eid, self.profile.vehicle_class):
                edge = self.map.edge_attributes(nxt)
                grade = edge.get("max_abs_grade")
                if grade is not None and grade > self.profile.max_grade:
                    continue
                travel = edge["length_m"]/edge["speed_mps"]
                extra, forbidden = 0.0, False
                for observation in affected.get(nxt, []):
                    if observation.kind == "landslide":
                        forbidden = True
                    elif observation.kind == "flood":
                        depth = observation.facts["water_depth_m"]
                        forbidden |= depth > self.profile.max_water_depth_m
                        extra += depth*self.profile.water_risk_s_per_m
                    elif observation.kind == "congestion":
                        extra += travel*(1/observation.facts["traffic_speed_ratio"]-1)*self.profile.congestion_weight
                if forbidden:
                    continue
                # Connector cost accounts for junction gaps, making straight-line A* admissible.
                connector = math.dist(self.map.edges[eid]["shape_xy"][-1], edge["shape_xy"][0])/self.map.max_speed
                candidate = cost+travel+connector+extra+edge.get("uphill_gain_m", 0)*self.profile.uphill_s_per_m
                if candidate < costs.get(nxt, math.inf):
                    costs[nxt], parents[nxt] = candidate, eid
                    heapq.heappush(queue, (candidate+estimate(nxt), candidate, nxt))
        return None, math.inf
