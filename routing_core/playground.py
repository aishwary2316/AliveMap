"""Editable scenario intent and validation; no simulator or GUI imports."""
from copy import deepcopy
import math
import re

from shapely.geometry import Point, shape

from .agents import PROFILES, VehicleAgent

ROLES = {"reporter", "receiver", "both", "offline"}


def empty_scene(provider):
    return {"schema_version": 1, "map_id": provider.manifest["map_id"], "map_build_id": provider.manifest["build_id"],
            "vehicles": {}, "towers": [], "anomalies": []}


def road_placement(provider, lonlat, edge_id=None):
    x, y = provider.lonlat_to_xy(*lonlat)
    point = Point(x, y)
    eid = edge_id or provider.nearest_road(lonlat[1], lonlat[0], max_distance=50)
    if eid not in provider.edges or "passenger" not in provider.edges[eid]["allowed"] or provider.lines[eid].distance(point) > 50:
        raise ValueError("Choose an eligible road within 50 m; vehicles cannot spawn off-road")
    line = provider.lines[eid]
    position = line.project(point)/max(line.length, 1)*provider.edges[eid]["sumo_length_m"]
    position = max(0, min(position, max(0, provider.edges[eid]["sumo_length_m"]-6)))
    snapped = line.interpolate(line.project(point))
    return {"edge": eid, "position_m": position, "lonlat": list(provider.xy_to_lonlat(snapped.x, snapped.y))}


def validate_scene(provider, scene):
    scene = deepcopy(scene)
    if scene.get("schema_version") != 1 or scene.get("map_id") != provider.manifest["map_id"] or scene.get("map_build_id") != provider.manifest["build_id"]:
        raise ValueError("Scene belongs to another map/build; reopen the matching package")
    vehicles, towers, anomalies = scene.get("vehicles", {}), scene.get("towers", []), scene.get("anomalies", [])
    if len(vehicles) > 64 or len(towers) > 32 or len(anomalies) > 32:
        raise ValueError("Playground limit: 64 vehicles, 32 towers, 32 anomalies")
    west, south, east, north = provider.manifest["bounds_wgs84"]
    def inside(point):
        return len(point) == 2 and all(math.isfinite(v) for v in point) and west <= point[0] <= east and south <= point[1] <= north
    for name, vehicle in vehicles.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", name) or name == "operator":
            raise ValueError("Vehicle ID must use letters, numbers, underscore or hyphen (not operator)")
        if vehicle.get("profile") not in PROFILES or vehicle.get("role", "both") not in ROLES:
            raise ValueError("Unknown vehicle profile/role")
        origin, destination = vehicle["origin"], vehicle["destination"]
        route, _ = VehicleAgent(provider, PROFILES[vehicle["profile"]]).route(origin, destination)
        if route is None:
            raise ValueError(f"{name}: destination cannot be reached from that directed origin")
        if not 0 <= vehicle.get("position_m", 0) <= max(0, provider.edges[origin]["sumo_length_m"]-6):
            raise ValueError("Spawn position is outside the road")
    if len({t["id"] for t in towers}) != len(towers) or len({a["id"] for a in anomalies}) != len(anomalies):
        raise ValueError("Duplicate tower/anomaly IDs")
    for tower in towers:
        if not inside((tower["longitude"], tower["latitude"])) or not 50 <= tower["radius_m"] <= 10000:
            raise ValueError("Tower must lie inside map and have radius 50–10000 m")
    for anomaly in anomalies:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", anomaly["id"]) or anomaly["kind"] not in ("congestion", "flood", "landslide"):
            raise ValueError("Invalid anomaly ID/type")
        polygon = shape(anomaly["geometry"])
        if polygon.geom_type != "Polygon" or not polygon.is_valid or polygon.is_empty or len(polygon.exterior.coords) > 130 or polygon.interiors:
            raise ValueError("Use a valid circle, rectangle or non-intersecting polygon (max 129 vertices)")
        if not all(inside(point) for point in polygon.exterior.coords):
            raise ValueError("Anomaly lies outside this map extract")
        area = provider.geometry_to_xy(anomaly["geometry"]).area
        if not 1 <= area <= 25_000_000 or not provider.edges_intersecting_geometry(anomaly["geometry"]):
            raise ValueError("Anomaly must cover a real eligible road, with area 1 m²–25 km²")
        if not 0 <= anomaly.get("detect_m", 20) <= 100 or not 1 <= anomaly.get("ttl_s", 1800) <= 86400 or not 0 <= anomaly.get("water_depth_m", 0.25) <= 10 or not 0 < anomaly.get("traffic_speed_ratio", 0.08) <= 1:
            raise ValueError("Invalid lifetime/depth/speed ratio")
    return scene


def example_scene(provider, scenario):
    scene = empty_scene(provider)
    scene["vehicles"] = {name: {**deepcopy(v), "role": "both"} for name, v in scenario["vehicles"].items()}
    trip = scene["vehicles"]["cautious"]
    route, _ = VehicleAgent(provider, PROFILES[trip["profile"]]).route(trip["origin"], trip["destination"])
    anchor = scenario["hazard"]["anchor_edge"]
    if anchor in route:
        index = route.index(anchor)
        scene["vehicles"]["probe"] = {"origin": route[max(0, index-2)], "destination": route[min(len(route)-1, index+2)], "profile": "time_sensitive", "role": "both"}
    area = provider.geometry_to_xy(scenario["hazard"]["geometry"])
    lon, lat = provider.xy_to_lonlat(area.centroid.x, area.centroid.y)
    scene["towers"] = [{"id": "Sim-gNB-1", "longitude": lon, "latitude": lat, "radius_m": 3000}]
    scene["anomalies"] = [{"id": "anomaly-1", "kind": scenario["hazard"]["kind"], "geometry": deepcopy(scenario["hazard"]["geometry"]),
                           "ttl_s": 1800, "water_depth_m": 0.25, "traffic_speed_ratio": 0.08, "detect_m": 20}]
    return validate_scene(provider, scene)
