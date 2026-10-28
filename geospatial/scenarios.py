"""Find real, repeatable OD/incident sites; never store an alternate route."""
import random
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import networkx as nx

from routing_core.agents import Observation, PROFILES, VehicleAgent


def observation(provider, scenario, experiment_id, version=1, kind=None):
    now = datetime.now(timezone.utc)
    selected = kind or scenario["hazard"]["kind"]
    facts = {"congestion": {"traffic_speed_ratio": 0.08}, "flood": {"water_depth_m": 0.25}}.get(selected, {})
    if selected == scenario["hazard"]["kind"]:
        facts = dict(scenario["hazard"]["facts"])
    return Observation(experiment_id=experiment_id, map_id=provider.manifest["map_id"], event_version=version,
                       kind=selected, geometry=scenario["hazard"]["geometry"],
                       observed_at=now.isoformat(), expires_at=(now+timedelta(seconds=scenario.get("ttl_seconds", 1800))).isoformat(),
                       source_type="synthetic_scenario", facts=facts).validate()


def create_scenario(provider, kind):
    graph = nx.DiGraph()
    for eid in provider.edges:
        if "passenger" in provider.edges[eid]["allowed"]:
            graph.add_node(eid)
            graph.add_edges_from((eid, nxt) for nxt in provider.neighbors(eid))
    component = max(nx.strongly_connected_components(graph), key=len)
    candidates = sorted(eid for eid in component if provider.edges[eid]["length_m"] > 20)
    random.Random(42).shuffle(candidates)
    blue_name, orange_name = ("low_clearance", "high_clearance") if kind == "flood" else ("time_sensitive", "distance_focused")
    blue, orange = VehicleAgent(provider, PROFILES[blue_name]), VehicleAgent(provider, PROFILES[orange_name])
    fallback = None
    for index in range(min(120, len(candidates)//2)):
        origin, destination = candidates[index*2:index*2+2]
        if provider.edges[origin]["length_m"] > 300:
            continue
        route, cost = orange.route(origin, destination)
        if not route or len(route) < 6 or cost < 130 or cost > 700:
            continue
        for anchor in route[max(2, len(route)//3):max(3, 2*len(route)//3)]:
            line = provider.lines[anchor]
            if line.length < 30:
                continue
            area = line.interpolate(line.length/2).buffer(10, quad_segs=4)
            hazard = {"kind": kind, "geometry": provider.geometry_to_wgs84(area),
                      "facts": {"water_depth_m": 0.25} if kind == "flood" else {"traffic_speed_ratio": 0.08} if kind == "congestion" else {},
                      "source_type": "synthetic_scenario", "anchor_edge": anchor}
            scenario = {"schema_version": "1.0", "scenario_id": provider.manifest["package_id"]+"_"+kind,
                        "map_id": provider.manifest["map_id"], "map_build_id": provider.manifest["build_id"], "seed": 42,
                        "ttl_seconds": 1800, "hazard": hazard,
                        "vehicles": {"cautious": {"origin": origin, "destination": destination, "profile": blue_name},
                                     "standard": {"origin": origin, "destination": destination, "profile": orange_name}},
                        "events": [{"sim_time_s": 1, "kind": kind}, {"sim_time_s": 12, "kind": "landslide"}, {"sim_time_s": 100, "kind": "clear"}],
                        "label": "SYNTHETIC SCENARIO on real roads; no measured flood, landslide or traffic claim"}
            event = observation(provider, scenario, "build-validation")
            blue_route, _ = blue.route(origin, destination, [event])
            orange_route, _ = orange.route(origin, destination, [event])
            affected = set(provider.edges_intersecting_geometry(hazard["geometry"]))
            if not affected.intersection(route):
                continue
            scenario["validation"] = {"baseline_feasible": True, "affected_edges": sorted(affected),
                                      "blue_reroutes": blue_route is not None and blue_route != route,
                                      "orange_route_differs_from_blue": orange_route != blue_route,
                                      "no_feasible_route": blue_route is None,
                                      "largest_passenger_component_edges": len(component)}
            if blue_route is not None and blue_route != route and (kind == "landslide" or orange_route != blue_route):
                fallback = scenario
                break
            if kind == "landslide" and blue_route is None:
                fallback = scenario
        if fallback:
            break
    if fallback is None:
        raise ValueError("No meaningful real-road OD/hazard case found; expand/inspect footprint instead of inventing a detour")
    # Find an unaffected, valid trip through the same component; no route list is embedded.
    affected = set(fallback["validation"]["affected_edges"])
    for start, dest in zip(candidates[::2], candidates[1::2]):
        route, cost = orange.route(start, dest)
        if route and len(route) >= 3 and cost > 80 and not affected.intersection(route):
            fallback["vehicles"]["unaffected"] = {"origin": start, "destination": dest, "profile": orange_name}
            break
    if "unaffected" not in fallback["vehicles"]:
        raise ValueError("No validated unaffected trip found")
    return fallback


def validate_scenario(provider, scenario):
    if scenario["map_id"] != provider.manifest["map_id"] or scenario["map_build_id"] != provider.manifest["build_id"]:
        raise ValueError("Scenario references the wrong map/build")
    affected = provider.edges_intersecting_geometry(scenario["hazard"]["geometry"])
    if scenario["hazard"]["anchor_edge"] not in affected:
        raise ValueError("Scenario hazard does not overlap its declared road")
    for vehicle in scenario["vehicles"].values():
        route, _ = VehicleAgent(provider, PROFILES[vehicle["profile"]]).route(vehicle["origin"], vehicle["destination"])
        if route is None:
            raise ValueError("Scenario has an unreachable initial destination")
        provider.validate_route(route)
    return affected
