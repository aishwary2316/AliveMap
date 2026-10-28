"""Deterministic fictional grid near Imphal, plus directed lane map matching."""
import hashlib
import heapq
import math
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

import sumolib
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent
SCENARIO = ROOT / "scenario"


def binary(name):
    # Prefer the pinned wheel's binaries even if another SUMO is installed.
    import sumo
    candidate = Path(sumo.SUMO_HOME) / "bin" / (name + (".exe" if __import__("os").name == "nt" else ""))
    return str(candidate) if candidate.exists() else shutil.which(name) or sumolib.checkBinary(name)


def build():
    SCENARIO.mkdir(exist_ok=True)
    forward = Transformer.from_crs(4326, 32646, always_xy=True)
    inverse = Transformer.from_crs(32646, 4326, always_xy=True)
    ox, oy = forward.transform(93.94, 24.80)
    nodes, edges = ET.Element("nodes"), ET.Element("edges")
    for x in range(6):
        for y in range(6):
            lon, lat = inverse.transform(ox + 300*x, oy + 300*y)
            ET.SubElement(nodes, "node", id=f"n{x}_{y}", x=f"{lon:.10f}", y=f"{lat:.10f}", type="priority")
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                a, b = x + dx, y + dy
                if 0 <= a < 6 and 0 <= b < 6:
                    ET.SubElement(edges, "edge", id=f"n{x}_{y}__n{a}_{b}",
                                  **{"from": f"n{x}_{y}", "to": f"n{a}_{b}",
                                     "numLanes": "1", "speed": "10", "allow": "passenger"})
    ET.ElementTree(nodes).write(SCENARIO / "grid.nod.xml")
    ET.ElementTree(edges).write(SCENARIO / "grid.edg.xml")
    subprocess.run([binary("netconvert"), "--node-files", str(SCENARIO / "grid.nod.xml"),
                    "--edge-files", str(SCENARIO / "grid.edg.xml"), "--proj.utm", "--seed", "42",
                    "--no-turnarounds", "true", "--output-file", str(SCENARIO / "grid.net.xml")], check=True)
    # Remove netconvert's timestamp/absolute-path comment for a portable, repeatable network hash.
    tree = ET.parse(SCENARIO / "grid.net.xml")
    tree.write(SCENARIO / "grid.net.xml", encoding="utf-8", xml_declaration=True)
    config = ET.Element("configuration")
    inp = ET.SubElement(config, "input")
    ET.SubElement(inp, "net-file", value="grid.net.xml")
    ET.ElementTree(config).write(SCENARIO / "grid.sumocfg")


def load():
    path = SCENARIO / "grid.net.xml"
    return sumolib.net.readNet(str(path)), hashlib.sha256(path.read_bytes()).hexdigest()


def distance(point, shape):
    best = math.inf
    for a, b in zip(shape, shape[1:]):
        dx, dy = b[0]-a[0], b[1]-a[1]
        t = max(0, min(1, ((point[0]-a[0])*dx + (point[1]-a[1])*dy) / (dx*dx+dy*dy))) if dx or dy else 0
        best = min(best, math.hypot(point[0]-a[0]-t*dx, point[1]-a[1]-t*dy))
    return best


def match(net, lat, lon, max_distance=12):
    point = net.convertLonLat2XY(lon, lat)
    candidates = sorted((min(distance(point, lane.getShape()) for lane in e.getLanes()
                             if lane.allows("passenger")), e.getID())
                        for e in net.getEdges() if e.allows("passenger"))
    if not candidates or candidates[0][0] > max_distance:
        raise ValueError("Hazard is outside the mapped road lanes")
    if len(candidates) > 1 and candidates[1][0] - candidates[0][0] < 0.5:
        raise ValueError("Ambiguous directed lane match")
    return candidates[0][1], candidates[0][0]


def shortest(net, start, destination, hazards=None, warning_seconds=0):
    """Dijkstra over legal edge connections; no enumerated alternative routes.

    Current edge is mandatory and can be exited even if it becomes closed.
    Closed downstream edges are excluded, rather than assigned a finite penalty.
    """
    hazards = hazards or {}
    queue, costs, previous = [(0.0, start)], {start: 0.0}, {}
    while queue:
        cost, edge_id = heapq.heappop(queue)
        if cost != costs[edge_id]:
            continue
        if edge_id == destination:
            route = [edge_id]
            while route[-1] != start:
                route.append(previous[route[-1]])
            return list(reversed(route))
        edge = net.getEdge(edge_id)
        for nxt, connections in sorted(edge.getOutgoing().items(), key=lambda kv: kv[0].getID()):
            if not any(c.getFromLane().allows("passenger") and c.getToLane().allows("passenger")
                       for c in connections):
                continue
            key = nxt.getID()
            hazard = hazards.get(key, {})
            state = hazard.get("state")
            if state == "closed":
                continue
            weight = nxt.getLength() / nxt.getSpeed() + (warning_seconds * hazard["severity"] if state == "warning" else 0)
            new = cost + weight
            if new < costs.get(key, math.inf):
                costs[key], previous[key] = new, edge_id
                heapq.heappush(queue, (new, key))
    return None


if __name__ == "__main__":
    build()
