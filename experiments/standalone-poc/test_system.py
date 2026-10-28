import math
from uuid import uuid4

import pytest
import sumolib
from fastapi.testclient import TestClient

from controller import MecClient, mapped_hazards
from mec_api import create_app
from network import load, match, shortest


@pytest.fixture
def api(tmp_path):
    clock = [1000.0]
    token = "test-token-at-least-16-characters"
    path = tmp_path / "test.sqlite3"
    app = create_app(path, token, now=lambda: clock[0])
    client = TestClient(app, headers={"X-POC-Token": token})
    prefix = f"/v1/runs/{uuid4()}"
    payload = dict(hazard_id="road1", revision=1, network_id="a"*64, reporter="probe",
                   lat=24.8, lon=93.94, state="warning", ttl_seconds=10)
    return client, prefix, payload, clock, path, token


def test_auth_validation_and_health(api):
    client, prefix, payload, *_ = api
    assert client.get("/health").json()["status"] == "ok"
    assert client.get(prefix + "/semantics", headers={"X-POC-Token": "bad"}).status_code == 401
    assert client.post(prefix + "/hazards", json={**payload, "lat": 95}).status_code == 422
    assert client.post(prefix + "/hazards", json={**payload, "edge_id": "fake"}).status_code == 422


def test_revision_idempotency_conflict_clear_and_run_isolation(api):
    client, prefix, payload, *_ = api
    url = prefix + "/hazards"
    assert client.post(url, json=payload).json()["version"] == 1
    assert client.post(url, json=payload).json()["version"] == 1
    assert client.post(url, json={**payload, "state": "closed"}).status_code == 409
    assert client.post(url, json={**payload, "revision": 2, "state": "closed"}).json()["version"] == 2
    assert client.post(url, json=payload).status_code == 409
    assert client.get(f"/v1/runs/{uuid4()}/semantics").json()["hazards"] == []
    assert client.post(url, json={**payload, "revision": 3, "state": "clear"}).json()["version"] == 3
    assert client.get(prefix + "/semantics").json()["hazards"] == []


def test_ttl_persistence_and_no_retry_renewal(api):
    client, prefix, payload, clock, path, token = api
    client.post(prefix + "/hazards", json=payload)
    clock[0] += 8
    client.post(prefix + "/hazards", json=payload)
    restarted = TestClient(create_app(path, token, now=lambda: clock[0]),
                           headers={"X-POC-Token": token})
    assert restarted.get(prefix + "/semantics").json()["version"] == 1
    clock[0] += 3
    snapshot = restarted.get(prefix + "/semantics").json()
    assert snapshot["version"] == 2 and snapshot["hazards"] == []
    assert restarted.get(prefix + "/semantics").json()["version"] == 2


def midpoint(net, edge_id):
    shape = net.getEdge(edge_id).getLanes()[0].getShape()
    xy = sumolib.geomhelper.positionAtShapeOffset(shape, net.getEdge(edge_id).getLength()/2)
    lon, lat = net.convertXY2LonLat(*xy)
    return lat, lon


def test_directed_lane_roundtrip_and_far_point():
    net, _ = load()
    for edge in net.getEdges():
        lat, lon = midpoint(net, edge.getID())
        matched, dist = match(net, lat, lon)
        assert matched == edge.getID() and dist < 0.01
    with pytest.raises(ValueError, match="outside"):
        match(net, 0, 0)


def test_ambiguous_match_rejected():
    net, _ = load()
    forward = "n2_2__n3_2"
    reverse = "n3_2__n2_2"
    points = []
    for eid in (forward, reverse):
        lat, lon = midpoint(net, eid)
        points.append(net.convertLonLat2XY(lon, lat))
    lon, lat = net.convertXY2LonLat(*[(a+b)/2 for a, b in zip(*points)])
    with pytest.raises(ValueError, match="Ambiguous"):
        match(net, lat, lon)


def test_independent_costs_legal_connections_and_disconnection():
    net, _ = load()
    start, end = "n0_2__n1_2", "n4_2__n5_2"
    base = shortest(net, start, end)
    hazard = base[len(base)//2]
    warning = {hazard: "warning"}
    cautious = shortest(net, start, end, warning, 300)
    standard = shortest(net, start, end, warning, 0)
    assert hazard not in cautious and standard == base
    closed = shortest(net, start, end, {hazard: "closed"}, 0)
    assert hazard not in closed
    for route in (base, cautious, standard, closed):
        assert route[0] == start and route[-1] == end
        for a, b in zip(route, route[1:]):
            assert net.getEdge(b) in net.getEdge(a).getOutgoing()
    all_closed = {e.getID(): "closed" for e in net.getEdges()}
    assert shortest(net, start, end, all_closed) is None
    assert shortest(net, start, end, {start: "closed"})  # Can exit current edge.
    assert shortest(net, start, end) == base  # Clear recalculates, rather than restores a saved route.


def test_network_mismatch_and_closed_precedence():
    net, nid = load()
    lat, lon = midpoint(net, "n2_2__n3_2")
    raw = dict(hazard_id="a", revision=1, network_id=nid, reporter="probe", lat=lat,
               lon=lon, state="closed", ttl_seconds=600, h3_cell="metadata")
    states, evidence = mapped_hazards(net, nid, {"hazards": [raw, {**raw, "hazard_id": "b", "state": "warning"}]})
    assert states["n2_2__n3_2"] == "closed"
    with pytest.raises(ValueError, match="different"):
        mapped_hazards(net, "0"*64, {"hazards": [raw]})


def test_retry_identical_body_after_lost_response():
    import httpx
    client = MecClient("http://127.0.0.1", "test", str(uuid4()))
    requests = []

    def respond(request):
        requests.append(request.content)
        if len(requests) == 1:
            raise httpx.ReadTimeout("response lost", request=request)
        return httpx.Response(200, json={"version": 1})

    client.http.close()
    client.http = httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(respond))
    assert client.report({"revision": 1}) == {"version": 1}
    assert requests[0] == requests[1]
    client.close()


@pytest.mark.parametrize("status,expected", [(503, 3), (401, 1)])
def test_report_retry_exhaustion_and_auth_not_retried(status, expected):
    import httpx
    client = MecClient("http://127.0.0.1", "test", str(uuid4()))
    calls = []

    def respond(request):
        calls.append(request.content)
        return httpx.Response(status, json={"detail": "test failure"})

    client.http.close()
    client.http = httpx.Client(base_url="http://127.0.0.1", transport=httpx.MockTransport(respond))
    with pytest.raises(RuntimeError if status == 503 else httpx.HTTPStatusError):
        client.report({"revision": 1})
    assert len(calls) == expected and len(set(calls)) == 1
    client.close()
