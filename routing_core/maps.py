"""Typed map boundary and a JSON/GeoTIFF package provider independent of SUMO."""
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Protocol

import h3
import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import transform
from shapely.strtree import STRtree


class MapProvider(Protocol):
    def neighbors(self, edge_id: str, vehicle_type: str = "passenger") -> list[str]: ...
    def edge_attributes(self, edge_id: str) -> Mapping[str, Any]: ...
    def edges_intersecting_geometry(self, geometry_wgs84: Mapping, vehicle_type: str = "passenger") -> list[str]: ...
    def nearest_road(self, latitude: float, longitude: float, vehicle_type: str = "passenger") -> str: ...


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_package(path, require_complete=False, verify_hashes=True):
    path = Path(path).resolve()
    manifest = read_json(path / "manifest.json")
    if manifest.get("schema_version") != "1.0":
        raise ValueError("Unsupported map package schema")
    if not manifest.get("map_id") or len(manifest.get("build_id", "")) != 64:
        raise ValueError("Missing map identity/build hash")
    bounds = manifest.get("bounds_wgs84", [])
    if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds) or not (-180 <= bounds[0] < bounds[2] <= 180 and -90 <= bounds[1] < bounds[3] <= 90):
        raise ValueError("Invalid or placeholder geographic bounds")
    if bounds == [0, 0, 0, 0] or not str(manifest.get("metric_crs", "")).startswith("EPSG:"):
        raise ValueError("Placeholder CRS or bounds")
    crs = CRS.from_user_input(manifest["metric_crs"])
    if not crs.is_projected or any(axis.unit_name != "metre" for axis in crs.axis_info):
        raise ValueError("Map CRS must use projected metres")
    if not manifest.get("checksums"):
        raise ValueError("Package has no integrity checksums")
    for key in ("sumo_network", "sumo_config", "routing_graph", "road_attributes", "spatial_index", "provenance_file"):
        file = (path / manifest[key]).resolve()
        if not file.is_relative_to(path) or not file.is_file():
            raise ValueError(f"Missing/unsafe package file: {key}")
        if manifest[key] not in manifest["checksums"]:
            raise ValueError(f"Required package file is not checksummed: {key}")
    warnings = []
    for key in ("elevation_raster", "satellite_raster"):
        value = manifest.get(key)
        if not value:
            warnings.append({"code": "SOURCE_UNAVAILABLE", "source": key})
        elif not (path / value).resolve().is_relative_to(path) or not (path / value).is_file():
            raise ValueError(f"Declared raster missing/unsafe: {key}")
    if require_complete and warnings:
        raise ValueError("Map is not complete: " + str(warnings))
    if verify_hashes:
        for relative, expected in manifest.get("checksums", {}).items():
            file = (path / relative).resolve()
            if not file.is_relative_to(path) or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Package checksum mismatch: {relative}")
    return manifest, warnings


class PackageMapProvider:
    def __init__(self, path, verify_hashes=True):
        self.path = Path(path).resolve()
        self.manifest, self.warnings = validate_package(self.path, verify_hashes=verify_hashes)
        self.edges = read_json(self.path / self.manifest["routing_graph"])["edges"]
        self.attributes = read_json(self.path / self.manifest["road_attributes"])
        if not self.edges or set(self.edges) != set(self.attributes):
            raise ValueError("Road graph/attribute IDs disagree")
        for eid, edge in self.edges.items():
            if edge["id"] != eid or len(edge["shape_xy"]) < 2 or not edge["allowed"] or not 0 < edge["speed_mps"] < 100 or not edge["length_m"] > 0:
                raise ValueError("Invalid road attributes")
            for vclass, successors in edge["successors"].items():
                if any(nxt not in self.edges or vclass not in self.edges[nxt]["allowed"] for nxt in successors):
                    raise ValueError("Invalid directed road connection")
        self.index = read_json(self.path / self.manifest["spatial_index"])
        self._forward = Transformer.from_crs(4326, self.manifest["metric_crs"], always_xy=True)
        self._reverse = Transformer.from_crs(self.manifest["metric_crs"], 4326, always_xy=True)
        self.offset = self.manifest["sumo_offset"]
        self.lines = {key: LineString(edge["shape_xy"]) for key, edge in self.edges.items()}
        self.edge_ids = list(self.lines)
        self.tree = STRtree(list(self.lines.values()))
        self.cells = list(self.index[str(self.manifest["h3_resolutions"]["micro"])])
        self.cell_polygons = [self.cell_polygon(cell) for cell in self.cells]
        self.cell_tree = STRtree(self.cell_polygons)
        self.max_speed = max(e["speed_mps"] for e in self.edges.values())

    def lonlat_to_xy(self, lon, lat):
        x, y = self._forward.transform(lon, lat)
        if np.ndim(x):
            return np.asarray(x)+self.offset[0], np.asarray(y)+self.offset[1]
        return x+self.offset[0], y+self.offset[1]

    def xy_to_lonlat(self, x, y):
        return self._reverse.transform(np.asarray(x)-self.offset[0], np.asarray(y)-self.offset[1])

    def geometry_to_xy(self, geometry):
        return transform(self.lonlat_to_xy, shape(geometry))

    def geometry_to_wgs84(self, geometry):
        from shapely.geometry import mapping
        return mapping(transform(self.xy_to_lonlat, geometry))

    def cell_polygon(self, cell):
        return Polygon([self.lonlat_to_xy(lon, lat) for lat, lon in h3.cell_to_boundary(cell)])

    def neighbors(self, edge_id, vehicle_type="passenger"):
        return self.edges[edge_id]["successors"].get(vehicle_type, [])

    def edge_attributes(self, edge_id):
        return {**self.edges[edge_id], **self.attributes[edge_id]}

    def edges_intersecting_geometry(self, geometry_wgs84, vehicle_type="passenger"):
        geometry = self.geometry_to_xy(geometry_wgs84)
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError("Hazard geometry is empty or invalid")
        candidates = set()
        index = self.index[str(self.manifest["h3_resolutions"]["micro"])]
        for position in self.cell_tree.query(geometry, predicate="intersects"):
            candidates.update(index[self.cells[int(position)]])
        return sorted(eid for eid in candidates if vehicle_type in self.edges[eid]["allowed"] and self.lines[eid].intersects(geometry))

    def nearest_road(self, latitude, longitude, vehicle_type="passenger", max_distance=40):
        point = Point(self.lonlat_to_xy(longitude, latitude))
        candidates = [self.edge_ids[int(i)] for i in self.tree.query(point.buffer(max_distance))]
        candidates = [eid for eid in candidates if vehicle_type in self.edges[eid]["allowed"]]
        if not candidates:
            raise ValueError("No eligible road within map-match tolerance")
        eid = min(candidates, key=lambda key: (self.lines[key].distance(point), key))
        if self.lines[eid].distance(point) > max_distance:
            raise ValueError("Coordinate outside map-match tolerance")
        return eid

    def validate_route(self, route, vehicle_type="passenger"):
        if not route or any(eid not in self.edges or vehicle_type not in self.edges[eid]["allowed"] for eid in route):
            raise ValueError("Route contains an invalid/ineligible road")
        if any(b not in self.neighbors(a, vehicle_type) for a, b in zip(route, route[1:])):
            raise ValueError("Route violates directed connectivity or turn permissions")
