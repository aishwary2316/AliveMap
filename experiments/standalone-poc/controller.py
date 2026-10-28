"""Laptop SUMO+TraCI controller; reports and polls a local or tunneled MEC API."""
import argparse
import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx
import traci

from mec_api import Report
from network import SCENARIO, binary, load, match, shortest


class MecClient:
    def __init__(self, url, token, run):
        self.run = run
        self.http = httpx.Client(base_url=url.rstrip("/"), headers={"X-POC-Token": token},
                                 timeout=3, trust_env=False)
        self.path = f"/v1/runs/{run}"

    def report(self, payload):
        # Safe retry after lost response: same id, revision and complete body.
        last = None
        for attempt in range(3):
            try:
                result = self.http.post(self.path + "/hazards", json=payload)
                result.raise_for_status()
                return result.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise
                time.sleep(0.2 * (attempt + 1))
        raise RuntimeError("MEC report unacknowledged after three identical retries") from last

    def snapshot(self):
        result = self.http.get(self.path + "/semantics")
        result.raise_for_status()
        data = result.json()
        if data.get("schema") != 1 or data.get("run_id") != self.run:
            raise ValueError("Unexpected MEC snapshot schema/run")
        if not isinstance(data.get("version"), int) or data["version"] < 0:
            raise ValueError("Invalid semantic version")
        return data

    def close(self):
        self.http.close()


def mapped_hazards(net, network_id, snapshot):
    result, evidence = {}, []
    for raw in snapshot["hazards"]:
        item = Report.model_validate({k: v for k, v in raw.items() if k not in ("expires_at", "h3_cell")})
        if item.network_id != network_id:
            raise ValueError("MEC hazard references a different SUMO network")
        edge, metres = match(net, item.lat, item.lon)
        if item.state != "clear":
            if result.get(edge) != "closed":
                result[edge] = item.state
        evidence.append({"hazard_id": item.hazard_id, "edge": edge, "distance_m": metres,
                         "h3_cell": raw["h3_cell"], "state": item.state})
    return result, evidence


def run(args):
    net, network_id = load()
    run_id = str(uuid4())
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    events = []
    stream = (output / "events.jsonl").open("w", encoding="utf-8")

    def log(kind, **data):
        event = {"event": kind, **data}
        events.append(event)
        stream.write(json.dumps(event) + "\n")
        stream.flush()
        if kind in ("report", "decision", "outage", "summary"):
            print(json.dumps(event), flush=True)

    client = MecClient(args.mec_url, args.token or os.environ.get("POC_TOKEN", ""), run_id)
    connection = None
    try:
        initial = client.snapshot()  # Fail before starting SUMO if tunnel/token is wrong.
        if initial["version"] != 0:
            raise RuntimeError("Fresh run unexpectedly has existing state")
        label = "poc-" + run_id
        traci.start([binary("sumo-gui" if args.gui else "sumo"), "-c", str(SCENARIO / "grid.sumocfg"),
                     "--seed", "42", "--step-length", "0.5", "--no-step-log", "true",
                     "--time-to-teleport", "-1", "--collision.action", "warn",
                     "--tripinfo-output", str((output / "tripinfo.xml").resolve()),
                     "--collision-output", str((output / "collisions.xml").resolve())], label=label)
        connection = traci.getConnection(label)
        fleet = {
            "cautious": ("n0_2__n1_2", "n4_2__n5_2", 300),
            "standard": ("n0_2__n1_2", "n4_2__n5_2", 0),
            "unaffected": ("n0_5__n1_5", "n4_5__n5_5", 100),
        }
        baseline = {}
        for index, (vehicle, (origin, dest, _)) in enumerate(fleet.items()):
            route = shortest(net, origin, dest)
            assert route
            baseline[vehicle] = route
            connection.route.add(vehicle + "-initial", route)
            connection.vehicle.add(vehicle, vehicle + "-initial", depart="0", departPos=str(index * 25))
        # Endpoints are scenario inputs; the hazard edge is chosen from a computed route.
        hazard_edge = baseline["cautious"][len(baseline["cautious"]) // 2]
        connection.route.add("probe-route", [hazard_edge])
        connection.vehicle.add("probe", "probe-route", depart="0",
                               departPos=str(net.getEdge(hazard_edge).getLength() / 2))
        connection.vehicle.setSpeed("probe", 0)
        log("start", run_id=run_id, network_id=network_id, hazard_edge=hazard_edge,
            baseline=baseline, sumo_version=connection.getVersion(), mec_url=args.mec_url)
        states, version, applied = {}, -1, {}
        sent, position, arrived = 0, None, set()
        traversed = {vehicle: [] for vehicle in fleet}
        warning_detour_seen = False
        schedule = (1, args.closure_at, args.clear_at)
        if not 1 < args.closure_at < args.clear_at < args.max_seconds:
            raise ValueError("Require 1 < closure-at < clear-at < max-seconds")
        last_ok, outage = time.monotonic(), False
        for step in range(int(args.max_seconds * 2)):
            connection.simulationStep()
            sim = connection.simulation.getTime()
            if connection.simulation.getStartingTeleportNumber():
                log("teleport", sim=sim, count=connection.simulation.getStartingTeleportNumber())
            if connection.simulation.getCollidingVehiclesNumber():
                log("collision", sim=sim, count=connection.simulation.getCollidingVehiclesNumber())
            arrived.update(set(connection.simulation.getArrivedIDList()) & set(fleet))
            if position is None and "probe" in connection.vehicle.getIDList():
                x, y = connection.vehicle.getPosition("probe")
                lon, lat = net.convertXY2LonLat(x, y)
                mapped, dist = match(net, lat, lon)
                assert mapped == connection.vehicle.getRoadID("probe") == hazard_edge
                position = (lat, lon)
                log("probe_position", sim=sim, lat=lat, lon=lon, actual_edge=hazard_edge,
                    mapped_edge=mapped, distance_m=dist)
            if position and sent < 3 and sim >= schedule[sent]:
                state = ("warning", "closed", "clear")[sent]
                payload = dict(hazard_id="demo-road", revision=sent+1, network_id=network_id,
                               reporter="probe", lat=position[0], lon=position[1],
                               state=state, ttl_seconds=600)
                response = client.report(payload)
                log("report", sim=sim, payload=payload, response=response)
                sent += 1
                if sent == 3:
                    connection.vehicle.remove("probe")
            if step % 2 == 0:
                try:
                    snapshot = client.snapshot()
                    if snapshot["version"] < version:
                        raise ValueError("MEC semantic version regressed")
                    if snapshot["version"] != version:
                        states, evidence = mapped_hazards(net, network_id, snapshot)
                        version = snapshot["version"]
                        log("semantic_update", sim=sim, version=version, mapping=evidence)
                    if outage:
                        log("reconnected", sim=sim)
                    last_ok, outage = time.monotonic(), False
                except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                        raise
                    if not outage:
                        log("outage", sim=sim, action="retain last acknowledged semantics")
                    outage = True
                    if time.monotonic() - last_ok > 10:
                        raise RuntimeError("MEC unavailable for >10 wall-clock seconds; stopping POC") from exc
            for vehicle in connection.vehicle.getIDList():
                if vehicle not in fleet or applied.get(vehicle) == version:
                    continue
                edge = connection.vehicle.getRoadID(vehicle)
                if edge.startswith(":"):
                    continue  # Defer until vehicle leaves junction; setRoute starts on current edge.
                dest, risk = fleet[vehicle][1:]
                before = list(connection.vehicle.getRoute(vehicle))[connection.vehicle.getRouteIndex(vehicle):]
                route = shortest(net, edge, dest, states, risk)
                if route is None:
                    connection.vehicle.setSpeed(vehicle, 0)
                    log("no_route", sim=sim, vehicle=vehicle, version=version)
                else:
                    connection.vehicle.setRoute(vehicle, route)
                    connection.vehicle.setSpeed(vehicle, -1)
                    assert connection.vehicle.isRouteValid(vehicle)
                    log("decision", sim=sim, version=version, vehicle=vehicle,
                        warning_seconds=risk, before=before, after=route, changed=before != route)
                applied[vehicle] = version
            for vehicle in connection.vehicle.getIDList():
                if vehicle in fleet:
                    edge = connection.vehicle.getRoadID(vehicle)
                    if not edge.startswith(":") and (not traversed[vehicle] or traversed[vehicle][-1] != edge):
                        traversed[vehicle].append(edge)
                        log("entered_edge", sim=sim, vehicle=vehicle, edge=edge, version=version)
            if version == 1 and any(e not in baseline["cautious"] for e in traversed["cautious"]):
                warning_detour_seen = True
            if args.pace:
                time.sleep(args.pace)
            if len(arrived) == len(fleet) and sent == 3:
                break
        summary = {"run_id": run_id, "network_id": network_id, "arrived": sorted(arrived),
                   "reports_acknowledged": sent, "last_version": version, "sim_seconds": sim,
                   "traversed": traversed,
                   "teleports": sum(e.get("count", 0) for e in events if e["event"] == "teleport")}
        decisions = [e for e in events if e["event"] == "decision"]
        lookup = {(e["version"], e["vehicle"]): e for e in decisions}
        checks = {
            "all_arrived": arrived == set(fleet),
            "no_collisions_or_teleports": not any(e["event"] in ("collision", "teleport") for e in events),
            "three_acknowledged_updates": sent == 3 and version == 3,
            "cautious_avoids_warning": lookup.get((1, "cautious"), {}).get("changed") is True,
            "standard_keeps_warning_route": lookup.get((1, "standard"), {}).get("changed") is False,
            "standard_avoids_closure": lookup.get((2, "standard"), {}).get("changed") is True,
            "closure_absent_all_routes": all(hazard_edge not in e["after"] for e in decisions if e["version"] == 2),
            "clear_recomputed_for_both": all((3, v) in lookup for v in ("cautious", "standard")),
            "cautious_drives_detour_during_warning": warning_detour_seen,
            "both_physically_drive_detours": all(any(e not in baseline[v] for e in traversed[v]) for v in ("cautious", "standard")),
            "unaffected_keeps_route": all(not e["changed"] for e in decisions if e["vehicle"] == "unaffected"),
        }
        summary["checks"] = checks
        summary["passed"] = all(checks.values())
        log("summary", **summary)
        (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if not summary["passed"]:
            raise RuntimeError("Acceptance checks failed; inspect summary.json and events.jsonl")
        return summary
    finally:
        if connection:
            connection.close()
        client.close()
        stream.close()


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--mec-url", default="http://127.0.0.1:8766")
    result.add_argument("--token", help="Prefer POC_TOKEN environment variable")
    result.add_argument("--output", default="runs/latest")
    result.add_argument("--gui", action="store_true")
    result.add_argument("--pace", type=float, default=0.02, help="Wall-clock pause per 0.5s simulation step")
    result.add_argument("--max-seconds", type=int, default=600)
    result.add_argument("--closure-at", type=float, default=45, help="Simulation seconds")
    result.add_argument("--clear-at", type=float, default=100, help="Simulation seconds")
    return result


if __name__ == "__main__":
    run(parser().parse_args())
