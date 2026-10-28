import io
import queue
import time
from types import SimpleNamespace

import pytest
from PIL import Image

from laptop.lab import LabWorker
from laptop.map_canvas import TileSource, TileStore, pixel_lonlat, world_pixel
from laptop.map_launcher import available_packages


@pytest.mark.parametrize("point", [(77.25, 28.63), (72.72, 21.12), (94.023, 25.28)])
def test_tile_coordinate_roundtrip(point):
    for zoom in (6, 16, 19):
        assert pixel_lonlat(*world_pixel(*point, zoom), zoom) == pytest.approx(point, abs=1e-9)


def test_visible_tile_cache_reuses_response_and_does_not_request_higher_zoom(tmp_path):
    data = io.BytesIO()
    Image.new("RGB", (256, 256), "green").save(data, format="PNG")
    calls = []
    class Response(io.BytesIO):
        headers = {"Cache-Control": "max-age=604800"}
    def fetch(request, timeout):
        calls.append(request)
        return Response(data.getvalue())
    store = TileStore(tmp_path, fetch=fetch)
    source = TileSource("test", "https://example.org/{z}/{x}/{y}.png", "test attribution", 19)
    assert store.load(source, 17, 10, 20).size == (256, 256)
    store.load(source, 17, 10, 20)
    assert len(calls) == 1 and "17/10/20" in calls[0].full_url
    assert calls[0].get_header("User-agent").startswith("AliveMap/")


def test_guided_worker_runs_every_map_at_fast_speed_without_ssh_and_keeps_epochs_separate(tmp_path):
    packages = available_packages()
    if len(packages) != 4 or any(not (p/"sumo/network.net.xml").exists() for p in packages.values()):
        pytest.skip("Build the four real map assets first")
    args = SimpleNamespace(gui=False, defer_start=True, map_package=None, scenario=None, mec_mode="local",
                           mec_url="http://127.0.0.1", semantics_url=None, output=str(tmp_path))
    worker = LabWorker(args)
    worker.start()
    epochs, reports, decisions = set(), [], []
    try:
        for name, path in packages.items():
            worker.commands.put(("load", (str(path), None, {"mec_mode": "local", "gui": False})))
            worker.commands.put(("speed", 100))
            deadline, latest = time.monotonic()+100, None
            while time.monotonic() < deadline:
                update = worker.updates.get(timeout=30)
                assert update["kind"] != "error", update
                if update["kind"] == "report":
                    reports.append(update)
                if update["kind"] == "decision":
                    decisions.append(update)
                if update["kind"] == "frame" and update["map_id"] == name:
                    latest = update
                    if update["complete"]:
                        break
            assert latest and latest["complete"] and len(latest["arrived"]) == 3
            assert latest["mec_mode"] == "local" and latest["requested_speed"] == 100
            assert latest["run_id"] not in epochs
            epochs.add(latest["run_id"])
        assert len(reports) == 12
        assert any(update.get("after") is None for update in decisions)
    finally:
        worker.commands.put(("stop", None))
        worker.join(timeout=20)
        assert not worker.is_alive()
