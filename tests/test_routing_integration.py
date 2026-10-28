import json
import urllib.error
from pathlib import Path
from uuid import uuid4

import pytest
import sumolib
import httpx
from fastapi.testclient import TestClient

from laptop.controller import mapped_hazards
from laptop.mec_client import MecClient, revision
from laptop.network import load, match, shortest
from mec.baseline import main
from mec.semantic_view import create_app


@pytest.fixture
def clients():
    main.events.clear()
    with TestClient(main.app) as upstream:
        client = MecClient("http://127.0.0.1:18765", str(uuid4()), "a"*64, http=upstream)
        yield client, upstream


def test_actual_client_contract_isolation_and_timestamp_independent_updates(clients):
    client, upstream = clients
    schema = json.loads((Path(__file__).resolve().parents[1] / "mec/baseline/openapi-observed.json").read_text())
    client.preflight(schema)
    other = dict(event_id="existing", vehicle_id="existing", latitude=0, longitude=0,
                 severity=0.5, event_type="existing")
    original = upstream.post("/hazards", json=other).json()["event"]
    assert client.snapshot()["version"] == 0
    payload, response = client.report("warning", 24.8, 93.94)
    assert set(payload) == set(other) and response["accepted"]
    assert client.snapshot()["version"] == 1
    client.report("warning", 24.8, 93.94)
    assert client.snapshot()["version"] == 1  # Receipt timestamp changed; meaning did not.
    client.report("closed", 24.8, 93.94)
    assert client.snapshot()["version"] == 2
    client.report("clear", 24.8, 93.94)
    assert client.snapshot()["version"] == 3
    assert main.events["existing"] == original


def test_state_loss_does_not_imply_clear(clients):
    client, _ = clients
    client.report("closed", 24.8, 93.94)
    client.snapshot()
    main.events.clear()
    with pytest.raises(RuntimeError, match="disappeared"):
        client.snapshot()


def test_transient_snapshot_disconnect_is_retried_without_changing_semantics(clients):
    client, upstream = clients
    calls = []

    def get_snapshot(request):
        calls.append(request.url.path)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError("Server disconnected", request=request)
        response = upstream.get(request.url.path)
        return httpx.Response(response.status_code, json=response.json())

    with httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(get_snapshot)) as transport:
        client.http = transport
        assert client.snapshot()["version"] == 0
        assert calls == ["/hazards", "/hazards"]
    client.http = upstream


def test_lost_report_response_retries_same_real_payload(clients):
    client, upstream = clients
    requests = []

    def deliver(request):
        response = upstream.request(request.method, request.url.path, content=request.content,
                                    headers={"Content-Type": "application/json"})
        if request.method == "POST":
            requests.append(request.content)
            if len(requests) == 1:
                raise httpx.ReadTimeout("Acknowledgement lost after server accepted report", request=request)
        return httpx.Response(response.status_code, json=response.json())

    with httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(deliver)) as transport:
        client.http = transport
        client.report("warning", 24.8, 93.94)
        assert len(requests) == 2 and requests[0] == requests[1]
        assert client.snapshot()["version"] == 1
        assert len(main.events) == 1
    client.http = upstream


def test_all_acknowledgements_lost_still_requires_abort_cleanup(clients):
    client, upstream = clients
    calls = []

    def lose_response(request):
        upstream.post("/hazards", content=request.content, headers={"Content-Type": "application/json"})
        calls.append(request.content)
        raise httpx.ReadTimeout("Server accepted it but response was lost", request=request)

    with httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(lose_response)) as transport:
        client.http = transport
        with pytest.raises(RuntimeError, match="three attempts"):
            client.report("closed", 24.8, 93.94)
        assert len(calls) == 3 and len(set(calls)) == 1
        assert client.attempted_report and not client.acknowledged_ids
    client.http = upstream
    client.report("clear", 24.8, 93.94)
    assert client.snapshot()["hazards"][0]["event_type"] == "alivemap.clear"


def test_bad_h3_or_unrecognized_semantics_fail_visibly(clients):
    client, _ = clients
    payload, _ = client.report("warning", 24.8, 93.94)
    main.events[payload["event_id"]]["h3_cell"] = "invalid"
    with pytest.raises(ValueError, match="resolution 10"):
        client.snapshot()
    client.report("warning", 24.8, 93.94)
    main.events[payload["event_id"]]["event_type"] = "unrecognized"
    with pytest.raises(ValueError, match="Unrecognized"):
        client.snapshot()


def test_semantic_view_reads_same_store_and_ignores_only_receipt_timestamp(clients):
    client, upstream = clients
    with TestClient(create_app(fetch=lambda path: upstream.get(path).json())) as view:
        assert view.get("/health").status_code == 200
        assert view.get("/semantics").status_code == 422  # Explicit prefix required.
        client.report("warning", 24.8, 93.94)
        first = view.get("/semantics", params={"prefix": client.prefix}).json()
        assert first["revision"] == revision(client.snapshot()["hazards"])
        client.report("warning", 24.8, 93.94)
        assert view.get("/semantics", params={"prefix": client.prefix}).json()["revision"] == first["revision"]
        client.report("closed", 24.8, 93.94)
        assert view.get("/semantics", params={"prefix": client.prefix}).json()["revision"] != first["revision"]
        assert len(main.events) == 1  # The view has no second hazard store.


def test_semantic_view_outage_is_503():
    def unavailable(path):
        raise urllib.error.URLError("upstream offline")
    with TestClient(create_app(fetch=unavailable)) as view:
        response = view.get("/semantics", params={"prefix": "alivemap:"})
        assert response.status_code == 503
        assert "events" not in response.json()


def test_semantic_view_does_not_label_unhealthy_upstream_healthy():
    with TestClient(create_app(fetch=lambda path: {"service": "mec-av-poc", "status": "error"})) as view:
        assert view.get("/health").status_code == 503


def midpoint(net, edge):
    lane = net.getEdge(edge).getLanes()[0]
    xy = sumolib.geomhelper.positionAtShapeOffset(lane.getShape(), lane.getLength()/2)
    lon, lat = net.convertXY2LonLat(*xy)
    return lat, lon


def test_all_120_directed_lanes_map_to_their_own_edge():
    net, _ = load()
    assert len(net.getEdges()) == 120
    for edge in net.getEdges():
        actual, distance = match(net, *midpoint(net, edge.getID()))
        assert actual == edge.getID() and distance < 0.01
    with pytest.raises(ValueError, match="outside"):
        match(net, 0, 0)
    a = net.convertLonLat2XY(*reversed(midpoint(net, "n2_2__n3_2")))
    b = net.convertLonLat2XY(*reversed(midpoint(net, "n3_2__n2_2")))
    lon, lat = net.convertXY2LonLat((a[0]+b[0])/2, (a[1]+b[1])/2)
    with pytest.raises(ValueError, match="Ambiguous"):
        match(net, lat, lon)


def test_independent_severity_costs_closures_and_actual_turn_connections():
    net, _ = load()
    start, dest = "n0_2__n1_2", "n4_2__n5_2"
    base = shortest(net, start, dest)
    hazard = base[len(base)//2]
    warning = {hazard: {"state": "warning", "severity": 0.7}}
    cautious = shortest(net, start, dest, warning, 300)
    standard = shortest(net, start, dest, warning, 0)
    assert hazard not in cautious and standard == base
    low = {hazard: {"state": "warning", "severity": 0.01}}
    assert shortest(net, start, dest, low, 300) == base
    closed = shortest(net, start, dest, {hazard: {"state": "closed", "severity": 1}}, 0)
    assert hazard not in closed
    for route in (base, cautious, standard, closed):
        assert route[0] == start and route[-1] == dest
        assert all(net.getEdge(b) in net.getEdge(a).getOutgoing() for a, b in zip(route, route[1:]))
    assert shortest(net, start, dest, {e.getID(): {"state": "closed"} for e in net.getEdges()}) is None


def test_multiple_reports_on_same_edge_use_closure_then_highest_warning():
    net, nid = load()
    lat, lon = midpoint(net, "n2_2__n3_2")
    event = dict(event_id="a", latitude=lat, longitude=lon, h3_cell="metadata",
                 event_type="alivemap.warning", severity=0.9)
    closed = {**event, "event_id": "b", "event_type": "alivemap.closed", "severity": 1}
    states, _ = mapped_hazards(net, nid, {"hazards": [closed, event]})
    assert states["n2_2__n3_2"]["state"] == "closed"
    states, _ = mapped_hazards(net, nid, {"hazards": [event, {**event, "severity": 0.1}]})
    assert states["n2_2__n3_2"]["severity"] == 0.9
