from types import SimpleNamespace

from fastapi.testclient import TestClient

from geospatial.scenarios import observation
from laptop.geo_session import GeoSession
from mec.baseline import main
from tests.test_geo_maps import package


def run_args(tmp_path, kind, name="delhi_urban"):
    return SimpleNamespace(gui=False, mec_url="http://127.0.0.1", semantics_url=None, output=str(tmp_path),
                           map_package=package(name), incident_kind=kind, incident_at=20)


def test_same_trip_clear_vs_incident_has_real_driven_detour_and_retained_old_plan(tmp_path):
    runs = {}
    for kind in ("none", "congestion"):
        session = GeoSession(run_args(tmp_path/kind, kind), http=TestClient(main.app))
        try:
            initial = {name: list(route) for name, route in session.baseline.items()}
            while session.sim_time < 20:
                session.step()
            assert not any(session.frame()["reroute_counts"].values())
            assert not session.client.attempted_report
            if kind != "none":
                session.report(kind)
                changed = session.frame()
                assert changed["reroute_counts"]["cautious"] == 1
                assert changed["route_history"]["cautious"][0]["old"] == initial["cautious"]
                assert changed["planned_routes"]["cautious"] != initial["cautious"]
            while not session.complete and session.sim_time < 1500:
                session.step()
            assert session.complete
            frame = session.frame()
            affected = set(session.provider.edges_intersecting_geometry(session.scenario["hazard"]["geometry"]))
            runs[kind] = (initial, frame, affected)
        finally:
            session.close()
    assert runs["none"][0] == runs["congestion"][0]
    assert not any(runs["none"][1]["reroute_counts"].values())
    assert runs["none"][2].intersection(runs["none"][1]["driven_edges"]["cautious"])
    assert not runs["congestion"][2].intersection(runs["congestion"][1]["driven_edges"]["cautious"])
    assert runs["congestion"][2].intersection(runs["congestion"][1]["driven_edges"]["standard"])


def test_other_incident_types_validate_and_no_route_is_not_called_a_reroute(tmp_path):
    session = GeoSession(run_args(tmp_path, "none", "manipur_mayangkhang"), http=TestClient(main.app))
    try:
        for kind in ("congestion", "flood", "landslide", "clear"):
            fact = observation(session.provider, session.scenario, session.run_id, kind=kind)
            fact.validate()
        session.report("landslide")
        frame = session.frame()
        assert frame["comparison_condition"] == "manual:landslide"
        assert "cautious" in frame["blocked"]
        assert frame["vehicles"]["cautious"]["route"] == []
        assert frame["reroute_counts"]["cautious"] == 0
        assert frame["route_history"]["cautious"][-1]["new"] is None
        session.report("clear")
        assert "cautious" not in session.frame()["blocked"]
    finally:
        session.close()


def test_worker_pauses_at_actual_reroute_and_resume_does_not_repeat_pause(tmp_path):
    import time
    from laptop.lab import LabWorker
    args = run_args(tmp_path, "congestion")
    args.defer_start, args.mec_mode, args.pause_on_change = True, "local", True
    worker = LabWorker(args)
    worker.start()
    try:
        worker.commands.put(("load", (str(args.map_package), None)))
        worker.commands.put(("speed", 100))
        deadline, reviewed = time.monotonic()+40, None
        while time.monotonic() < deadline:
            update = worker.updates.get(timeout=20)
            assert update["kind"] != "error", update
            if update["kind"] == "frame" and update["time"] >= 20 and not update["playing"]:
                reviewed = update
                break
        assert reviewed and reviewed["time"] == 20
        assert reviewed["reroute_counts"]["cautious"] == 1
        assert reviewed["route_history"]["cautious"][0]["old"] == reviewed["baseline_routes"]["cautious"]
        worker.commands.put(("play", None, reviewed["run_id"]))
        while time.monotonic() < deadline:
            update = worker.updates.get(timeout=20)
            if update["kind"] == "frame" and update["time"] >= 25:
                assert update["playing"]
                break
        else:
            raise AssertionError("Resume did not continue beyond the inspected reroute")
    finally:
        worker.commands.put(("stop", None))
        worker.join(timeout=20)
        assert not worker.is_alive()


def test_clock_and_fixed_overview_projection():
    from laptop.map_launcher import clock_text
    from laptop.route_minimap import fit_transform
    assert clock_text(3661.5) == "01:01:01.5"
    assert clock_text(0) == "00:00:00.0"
    project = fit_transform((100, 200, 1100, 700), 340, 166)
    west, south = project(100, 200)
    east, north = project(1100, 700)
    assert 0 <= west < east <= 340 and 0 <= north < south <= 166
