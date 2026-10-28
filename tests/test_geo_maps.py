import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from laptop.geo_session import GeoSession
from laptop.geo_mec import GeoMecClient
from geospatial.scenarios import observation
from routing_core.agents import PROFILES, VehicleAgent, Observation
from routing_core.maps import PackageMapProvider, read_json, validate_package
from mec.baseline import main

ROOT = Path(__file__).resolve().parents[1]


def package(name="delhi_urban"):
    folder = ROOT/"map_packages"/name
    if not (folder/"active.json").exists():
        pytest.skip("Build the real map package to run this integration test")
    path = folder/json.loads((folder/"active.json").read_text())["revision"]
    if not (path/"sumo/network.net.xml").is_file():
        pytest.skip("Map source assets are intentionally outside Git; run geospatial.build")
    return path


def test_real_delhi_mec_facts_change_independent_routes_and_are_driven(tmp_path):
    main.events.clear()
    args = SimpleNamespace(gui=False, mec_url="http://127.0.0.1", semantics_url=None,
                           output=str(tmp_path), map_package=package())
    events = []
    session = GeoSession(args, lambda kind, **data: events.append({"kind": kind, **data}), http=TestClient(main.app))
    try:
        # Ensure both queued same-origin vehicles enter before reporting.
        for _ in range(20):
            if set(session.frame()["vehicles"]) == set(session.fleet):
                break
            session.step()
        assert set(session.frame()["vehicles"]) == set(session.fleet)
        session.report("warning")
        frame = session.frame()
        affected = set(session.mapping[0]["edges"])
        assert not affected.intersection(frame["vehicles"]["cautious"]["route"])
        assert affected.intersection(frame["vehicles"]["standard"]["route"])
        assert frame["vehicles"]["cautious"]["route"] != frame["vehicles"]["standard"]["route"]
        driven = {v: set() for v in session.fleet}
        while not session.complete and session.sim_time < 1400:
            for name, state in session.frame()["vehicles"].items():
                driven[name].add(state["edge"])
            session.step()
        assert session.complete, session.frame()
        assert not affected.intersection(driven["cautious"])
        assert affected.intersection(driven["standard"])
        assert any(e["kind"] == "report" and e["response"]["event"]["h3_cell"] for e in events)
    finally:
        session.close()


@pytest.fixture(scope="module")
def real_map():
    return PackageMapProvider(package())


def test_geometric_index_matches_exhaustive_intersection_including_cell_crossings(real_map):
    p = real_map
    scenario = read_json(p.path/p.manifest["scenario"])
    area = p.geometry_to_xy(scenario["hazard"]["geometry"])
    expected = sorted(eid for eid, line in p.lines.items() if "passenger" in p.edges[eid]["allowed"] and line.intersects(area))
    assert p.edges_intersecting_geometry(scenario["hazard"]["geometry"]) == expected
    index = p.index["10"]
    counts = {}
    for cell, edges in index.items():
        for eid in edges:
            counts[eid] = counts.get(eid, 0)+1
    crossed = next(eid for eid in sorted(counts) if counts[eid] > 2 and "passenger" in p.edges[eid]["allowed"])
    area = p.lines[crossed].buffer(2)
    geometry = p.geometry_to_wgs84(area)
    actual = p.edges_intersecting_geometry(geometry)
    expected = sorted(eid for eid, line in p.lines.items() if "passenger" in p.edges[eid]["allowed"] and line.intersects(area))
    assert actual == expected and crossed in actual


def test_astar_matches_dijkstra_and_oneway_is_enforced(real_map):
    scenario = read_json(real_map.path/real_map.manifest["scenario"])
    fact = observation(real_map, scenario, "oracle")
    for profile in PROFILES.values():
        agent = VehicleAgent(real_map, profile)
        for vehicle in scenario["vehicles"].values():
            a, ac = agent.route(vehicle["origin"], vehicle["destination"], [fact])
            b, bc = agent.route(vehicle["origin"], vehicle["destination"], [fact], heuristic=False)
            assert ac == pytest.approx(bc)
            assert (a is None) == (b is None)
    start = next(eid for eid in real_map.edges if real_map.neighbors(eid))
    with pytest.raises(ValueError):
        real_map.validate_route([start, "invented-edge"])
    pair = next((a, b) for a in real_map.edges for b in real_map.neighbors(a) if a not in real_map.neighbors(b))
    with pytest.raises(ValueError):
        real_map.validate_route(list(reversed(pair)))


def test_manifest_missing_imagery_corruption_and_placeholder_are_explicit(real_map, monkeypatch):
    import routing_core.maps as maps
    original = maps.read_json
    manifest = dict(real_map.manifest)
    monkeypatch.setattr(maps, "read_json", lambda path: manifest if Path(path).name == "manifest.json" else original(path))
    manifest["satellite_raster"] = None
    assert validate_package(real_map.path)[1] == [{"code": "SOURCE_UNAVAILABLE", "source": "satellite_raster"}]
    with pytest.raises(ValueError, match="not complete"):
        validate_package(real_map.path, require_complete=True)
    manifest["checksums"] = {**manifest["checksums"], manifest["routing_graph"]: "0"*64}
    with pytest.raises(ValueError, match="checksum"):
        validate_package(real_map.path)
    manifest["bounds_wgs84"] = [0, 0, 0, 0]
    with pytest.raises(ValueError, match="bounds"):
        validate_package(real_map.path)


def test_nodata_is_rejected_not_converted_into_grade(tmp_path):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    from shapely.geometry import LineString
    from geospatial.build import sample_terrain
    file = tmp_path/"dem.tif"
    with rasterio.open(file, "w", driver="GTiff", width=10, height=10, count=1, dtype="float32",
                       crs="EPSG:32643", transform=from_origin(0, 100, 10, 10), nodata=-9999) as dst:
        dst.write(np.full((1, 10, 10), -9999, dtype="float32"))
    with rasterio.open(file) as src:
        result = sample_terrain(LineString([(5, 95), (85, 15)]), src, [0, 0])
    assert result["elevation_quality"] == "nodata" and result["max_abs_grade"] is None


def test_epoch_scope_expiry_and_loss_of_acknowledged_state(real_map):
    from datetime import datetime, timedelta, timezone
    import httpx
    main.events.clear()
    scenario = read_json(real_map.path/real_map.manifest["scenario"])
    a = GeoMecClient("http://127.0.0.1", "epoch-A", real_map.manifest["map_id"], http=TestClient(main.app))
    b = GeoMecClient("http://127.0.0.1", "epoch-B", real_map.manifest["map_id"], http=TestClient(main.app))
    fact = observation(real_map, scenario, "epoch-A")
    a.report_fact(fact)
    assert len(a.facts()["facts"]) == 1 and b.facts()["facts"] == []
    assert a.facts(datetime.now(timezone.utc)+timedelta(hours=1))["facts"] == []
    with pytest.raises(ValueError, match="another experiment"):
        b.report_fact(fact)
    main.events.clear()
    with pytest.raises(RuntimeError, match="disappeared"):
        a.facts()
    broken = GeoMecClient("http://127.0.0.1", "outage", "map", http=httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(503, json={"detail": "unavailable"})), base_url="http://127.0.0.1"))
    with pytest.raises(httpx.HTTPStatusError):
        broken.facts()  # Never reinterpret failure as clear roads.
    a.close(); b.close(); broken.close()


def test_switch_all_regions_and_both_manipur_subregions_without_stale_commands(tmp_path):
    from laptop.geo_session import ScenarioController
    names = ["delhi_urban", "gujarat_coastal", "manipur_mantripukhri", "manipur_mayangkhang", "delhi_urban"]
    paths = [package(name) for name in names]
    main.events.clear()
    main.events["unrelated"] = {"keep": True}
    args = SimpleNamespace(gui=False, mec_url="http://127.0.0.1", semantics_url=None, output=str(tmp_path))
    controller = ScenarioController(args, http_factory=lambda: TestClient(main.app))
    old_epochs = []
    try:
        for path in paths:
            session = controller.activate(path)
            assert session.run_id not in old_epochs and session.sim_time == 0.5
            assert not session.facts and session.state == "clear"
            for old in old_epochs:
                assert controller.command(old, "report", "closed") is False
            session.report("warning")
            assert session.facts[0].experiment_id == session.run_id
            old_epochs.append(session.run_id)
            assert main.events["unrelated"] == {"keep": True}
    finally:
        controller.close()
