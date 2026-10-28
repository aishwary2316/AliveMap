"""Windows-native, versioned OSM/DEM/Sentinel -> actionable SUMO map packages."""
import argparse
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

import h3
import networkx as nx
import numpy as np
import rasterio
import sumolib
from PIL import Image
from pyproj import Transformer
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry import LineString, Polygon

from laptop.network import binary
from routing_core.maps import PackageMapProvider, validate_package
from . import acquisition

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ("passenger", "truck", "bus", "emergency")
RESOLUTIONS = (8, 10)


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8", newline="\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def warp(source, destination, crs, resolution):
    with rasterio.open(source) as src:
        transform, width, height = calculate_default_transform(src.crs, crs, src.width, src.height, *src.bounds, resolution=resolution)
        profile = src.profile.copy()
        profile.update(crs=crs, transform=transform, width=width, height=height, compress="deflate")
        with rasterio.open(destination, "w", **profile) as dst:
            for band in range(1, src.count+1):
                reproject(rasterio.band(src, band), rasterio.band(dst, band), src_transform=src.transform,
                          src_crs=src.crs, dst_transform=transform, dst_crs=crs,
                          src_nodata=src.nodata, dst_nodata=src.nodata,
                          resampling=Resampling.bilinear)


def sample_terrain(line, raster, offset):
    if raster is None:
        return {"elevation_quality": "unavailable", "mean_grade": None, "max_abs_grade": None, "uphill_gain_m": 0.0}
    distances = np.linspace(0, line.length, max(2, math.ceil(line.length/40)+1))
    points = [line.interpolate(float(d)) for d in distances]
    samples = list(raster.sample([(point.x-offset[0], point.y-offset[1]) for point in points], masked=True))
    if any(np.ma.is_masked(value[0]) or not np.isfinite(value[0]) or not -500 <= float(value[0]) <= 9000 for value in samples):
        return {"elevation_quality": "nodata", "mean_grade": None, "max_abs_grade": None, "uphill_gain_m": 0.0}
    values = np.array([float(value[0]) for value in samples])
    smoothed = np.array([np.median(values[max(0, i-1):min(len(values), i+2)]) for i in range(len(values))])
    # Retain endpoints; short edges cannot support invented fine-resolution gradients.
    if len(values) <= 3:
        smoothed = values
    delta, dx = np.diff(smoothed), np.diff(distances)
    grades = delta/np.maximum(dx, 1)
    quality = "valid_dsm_derived" if np.max(np.abs(grades)) <= 0.5 else "implausible_dsm_gradient"
    return {"elevation_quality": quality, "elevation_samples_m": [round(float(v), 3) for v in values],
            "sample_distances_m": [round(float(v), 3) for v in distances],
            "mean_grade": round(float((smoothed[-1]-smoothed[0])/max(line.length, 1)), 6) if quality.startswith("valid") else None,
            "max_abs_grade": round(float(np.max(np.abs(grades))), 6) if quality.startswith("valid") else None,
            "uphill_gain_m": round(float(np.maximum(delta, 0).sum()), 3) if quality.startswith("valid") else 0.0}


def export_graph(net, roads_file, dem_file):
    osm = ET.parse(roads_file).getroot()
    tags = {way.get("id"): {tag.get("k"): tag.get("v") for tag in way.findall("tag")} for way in osm.findall("way")}
    edges, attributes = {}, {}
    offset = net.getLocationOffset()
    raster = rasterio.open(dem_file) if dem_file.exists() else None
    try:
        for edge in net.getEdges():
            allowed = [vclass for vclass in CLASSES if edge.allows(vclass)]
            if not allowed:
                continue
            lane = next(lane for lane in edge.getLanes() if any(lane.allows(vclass) for vclass in allowed))
            xy = [list(point[:2]) for point in lane.getShape()]
            line = LineString(xy)
            if line.length <= 0:
                continue
            original = edge.getParam("origId") or lane.getParam("origId") or edge.getID().lstrip("-").split("#")[0]
            original_ids = str(original).replace(" ", ",").split(",")
            source_tags = {oid: tags[oid] for oid in original_ids if oid in tags}
            successors = {}
            for vclass in allowed:
                successors[vclass] = sorted(nxt.getID() for nxt, connections in edge.getOutgoing().items()
                    if any(c.getFromLane().allows(vclass) and c.getToLane().allows(vclass) for c in connections))
            edges[edge.getID()] = {"id": edge.getID(), "from": edge.getFromNode().getID(), "to": edge.getToNode().getID(),
                                  "length_m": max(float(edge.getLength()), line.length), "sumo_length_m": float(edge.getLength()),
                                  "speed_mps": float(edge.getSpeed()), "allowed": allowed, "shape_xy": xy,
                                  "shape_wgs84": [list(net.convertXY2LonLat(*point)) for point in xy],
                                  "successors": successors, "osm_ids": original_ids,
                                  "name": edge.getName(), "osm_tags": source_tags}
            attributes[edge.getID()] = sample_terrain(line, raster, offset)
    finally:
        if raster:
            raster.close()
    # Remove references to omitted non-routable edges.
    for edge in edges.values():
        edge["successors"] = {key: [nxt for nxt in values if nxt in edges] for key, values in edge["successors"].items()}
    return {"schema_version": "1.0", "edges": edges}, attributes


def spatial_index(net, graph):
    index, polygon_cache = {str(res): {} for res in RESOLUTIONS}, {}
    for eid, edge in graph["edges"].items():
        line = LineString(edge["shape_xy"])
        for resolution in RESOLUTIONS:
            spacing = min(100, h3.average_hexagon_edge_length(resolution, unit="m")*0.25)
            candidates = set()
            for distance in np.linspace(0, line.length, max(2, math.ceil(line.length/spacing)+1)):
                point = line.interpolate(float(distance))
                lon, lat = net.convertXY2LonLat(point.x, point.y)
                candidates.update(h3.grid_disk(h3.latlng_to_cell(lat, lon, resolution), 1))
            for cell in sorted(candidates):
                if cell not in polygon_cache:
                    polygon_cache[cell] = Polygon([net.convertLonLat2XY(lon, lat) for lat, lon in h3.cell_to_boundary(cell)])
                if line.intersects(polygon_cache[cell]):
                    index[str(resolution)].setdefault(cell, []).append(eid)
    return index


def build(package_id, reuse_probe=False, skip_rasters=False):
    definitions = json.loads((ROOT / "geospatial/definitions.json").read_text())
    definition = definitions[package_id]
    packages = ROOT / "map_packages"
    stage = packages / ".staging" / uuid4().hex[:10]
    for directory in (stage / "source", stage / "processed", stage / "sumo/background"):
        directory.mkdir(parents=True, exist_ok=True)
    provenance, warnings = {}, []
    source, processed, sim = stage / "source", stage / "processed", stage / "sumo"
    bounds = definition["bounds_wgs84"]
    print(f"[{package_id}] acquiring OSM", flush=True)
    if reuse_probe and package_id == "delhi_urban" and (ROOT / ".local/source-probes/roads.osm.xml").exists():
        shutil.copyfile(ROOT / ".local/source-probes/roads.osm.xml", source / "roads.osm.xml")
        provenance["roads"] = {"product": "OpenStreetMap road extract", "source_url": "https://overpass-api.de/api/interpreter",
                               "query": acquisition.osm_query(bounds), "acquired_at": acquisition.utc(),
                               "license": "ODbL-1.0", "attribution": "© OpenStreetMap contributors",
                               "license_url": "https://www.openstreetmap.org/copyright"}
    else:
        provenance["roads"] = acquisition.roads(bounds, source / "roads.osm.xml")
    print(f"[{package_id}] converting real roads", flush=True)
    command = [binary("netconvert"), "--osm-files", str(source / "roads.osm.xml"),
               "--output-file", str(sim / "network.net.xml"), "--proj.utm", "--geometry.remove", "true",
               "--keep-edges.by-vclass", ",".join(CLASSES), "--output.original-names", "true",
               "--junctions.join", "true", "--tls.guess-signals", "true", "--seed", "42",
               "--keep-edges.in-geo-boundary", ",".join(map(str, bounds))]
    converted = subprocess.run(command, capture_output=True, text=True)
    (processed / "netconvert.log").write_text(converted.stdout+converted.stderr, encoding="utf-8")
    if converted.returncode:
        raise RuntimeError(f"netconvert failed; inspect {processed / 'netconvert.log'}: {converted.stderr[-1500:]}")
    tree = ET.parse(sim / "network.net.xml")
    tree.write(sim / "network.net.xml", encoding="utf-8", xml_declaration=True)
    net = sumolib.net.readNet(str(sim / "network.net.xml"))
    if not net.hasGeoProj():
        raise ValueError("Converted network has no geographic projection")
    print(f"[{package_id}] {len(net.getEdges())} external edges; acquiring rasters", flush=True)
    for name, fetch in (("elevation", acquisition.elevation), ("satellite", acquisition.satellite)):
        try:
            if skip_rasters:
                raise RuntimeError("Raster acquisition explicitly skipped")
            provenance[name] = fetch(bounds, source)
            warp(source / f"{name}.tif", processed / f"{name}_metric.tif", definition["metric_crs"], 30 if name == "elevation" else 10)
        except Exception as exc:
            warnings.append({"code": "SOURCE_UNAVAILABLE", "source": name, "detail": str(exc)})
            provenance[name] = {"status": "unavailable", "attempted_at": acquisition.utc(), "error": str(exc)}
            print(f"[{package_id}] {name}: unavailable: {exc}", flush=True)
    print(f"[{package_id}] sampling terrain and building H3 geometry index", flush=True)
    graph, attributes = export_graph(net, source / "roads.osm.xml", processed / "elevation_metric.tif")
    write(processed / "graph.json", graph)
    write(processed / "road_attributes.json", attributes)
    write(processed / "spatial_index.json", spatial_index(net, graph))
    background = None
    if (processed / "satellite_metric.tif").exists():
        with rasterio.open(processed / "satellite_metric.tif") as raster:
            rgb = raster.read([1, 2, 3])
            Image.fromarray(np.moveaxis(rgb.astype(np.uint8), 0, -1)).save(sim / "background/satellite.png")
            center = ((raster.bounds.left+raster.bounds.right)/2, (raster.bounds.bottom+raster.bounds.top)/2)
            background = {"file": "background/satellite.png", "centerX": center[0]+net.getLocationOffset()[0],
                          "centerY": center[1]+net.getLocationOffset()[1], "width": raster.bounds.right-raster.bounds.left,
                          "height": raster.bounds.top-raster.bounds.bottom, "layer": -100}
    settings = ET.Element("viewsettings")
    if background:
        ET.SubElement(settings, "decal", **{key: str(value) for key, value in background.items()})
    ET.ElementTree(settings).write(sim / "view.xml", encoding="utf-8", xml_declaration=True)
    config = ET.Element("configuration")
    ET.SubElement(ET.SubElement(config, "input"), "net-file", value="network.net.xml")
    ET.SubElement(ET.SubElement(config, "gui_only"), "gui-settings-file", value="view.xml")
    ET.ElementTree(config).write(sim / "scenario.sumocfg", encoding="utf-8", xml_declaration=True)
    features = subprocess.run([binary("netconvert"), "--version"], capture_output=True, text=True).stdout
    help_text = subprocess.run([binary("netconvert"), "--help"], capture_output=True, text=True).stdout
    provenance["conversion"] = {"sumo_version": features.strip(), "heightmap_option_listed": "--heightmap.geotiff" in help_text,
                                "elevation_strategy": "standalone rasterio sampling; independent of native SUMO heightmap support",
                                "limitations": "OSM tags may be incomplete; netconvert warnings retained; no measured traffic or hydrodynamics",
                                "h3_index_method": "densify <= quarter average H3 edge, one-ring candidates, exact projected line/cell intersection",
                                "h3_average_edge_length_m": {str(r): h3.average_hexagon_edge_length(r, unit="m") for r in RESOLUTIONS}}
    if (processed / "elevation_metric.tif").exists():
        probe = subprocess.run([binary("netconvert"), "--sumo-net-file", str(sim / "network.net.xml"),
                                "--heightmap.geotiff", str(processed / "elevation_metric.tif"),
                                "--output-file", str(processed / "heightmap-probe.net.xml")], capture_output=True, text=True)
        provenance["conversion"]["native_heightmap_probe"] = {"exit_code": probe.returncode, "diagnostic": probe.stderr[-2000:]}
    write(processed / "provenance.json", provenance)
    files = {str(path.relative_to(stage)).replace("\\", "/"): sha(path) for path in stage.rglob("*") if path.is_file() and path.name != "netconvert.log"}
    identity = {"recipe": "alivemap-map-v1", "definition": definition,
                "sources": {key: value for key, value in files.items() if key.startswith("source/")},
                "sumo_version": features.strip()}
    build_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    manifest = {"schema_version": "1.0", **definition, "package_id": package_id, "build_id": build_id,
                "revision": build_id[:12], "built_at": acquisition.utc(), "source_crs": "EPSG:4326",
                "sumo_offset": list(net.getLocationOffset()), "sumo_network": "sumo/network.net.xml", "sumo_config": "sumo/scenario.sumocfg",
                "routing_graph": "processed/graph.json", "road_attributes": "processed/road_attributes.json",
                "spatial_index": "processed/spatial_index.json", "provenance_file": "processed/provenance.json",
                "elevation_raster": "source/elevation.tif" if (source / "elevation.tif").exists() else None,
                "satellite_raster": "source/satellite.tif" if (source / "satellite.tif").exists() else None,
                "background": background, "h3_version": h3.__version__, "h3_resolutions": {"macro": 8, "micro": 10},
                "warnings": warnings, "checksums": files, "edge_count": len(graph["edges"]),
                "terrain_valid_edges": sum(a["elevation_quality"] == "valid_dsm_derived" for a in attributes.values()),
                "status": "complete" if not warnings else "degraded"}
    write(stage / "manifest.json", manifest)
    validate_package(stage)
    # Validate geographic round trips before publishing an active pointer.
    provider = PackageMapProvider(stage)
    for edge in list(provider.edges.values())[::max(1, len(provider.edges)//20)]:
        for xy in (edge["shape_xy"][0], edge["shape_xy"][-1]):
            lon, lat = provider.xy_to_lonlat(*xy)
            if math.dist(xy, provider.lonlat_to_xy(lon, lat)) > 0.01:
                raise ValueError("Geographic round trip exceeds 1 cm")
    from .scenarios import create_scenario
    scenario = create_scenario(provider, definition["demonstration"])
    write(processed / "scenario.json", scenario)
    manifest["checksums"]["processed/scenario.json"] = sha(processed / "scenario.json")
    manifest["scenario"] = "processed/scenario.json"
    write(stage / "manifest.json", manifest)
    destination = packages / package_id / build_id[:12]
    if not stage.resolve().is_relative_to(packages.resolve()) or not destination.resolve().is_relative_to(packages.resolve()):
        raise ValueError("Unsafe map publication path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Build already exists; retained new staging files at {stage}")
    stage.rename(destination)
    write(destination.parent / "active.json", {"revision": build_id[:12], "build_id": build_id})
    print(f"[{package_id}] published {destination}; status={manifest['status']}; scenario={scenario['scenario_id']}", flush=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", choices=list(json.loads((ROOT / "geospatial/definitions.json").read_text())))
    parser.add_argument("--reuse-delhi-probe", action="store_true")
    parser.add_argument("--skip-rasters", action="store_true", help="Explicit degraded roads-only build; never reports complete")
    args = parser.parse_args()
    build(args.package, args.reuse_delhi_probe, args.skip_rasters)


if __name__ == "__main__":
    main()
