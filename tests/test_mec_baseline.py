"""Lock the real MEC contract before designing extensions. All calls are local."""
import importlib.util
import json
import sys
from pathlib import Path

import h3
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    spec = importlib.util.spec_from_file_location("observed_mec_baseline", ROOT / "mec/baseline/main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    with TestClient(module.app) as instance:
        yield instance


@pytest.fixture
def hazard():
    return {
        "event_id": "contract-test",
        "vehicle_id": "test-vehicle",
        "latitude": 24.8,
        "longitude": 93.94,
        "event_type": "test-hazard",
        "severity": 0.7,
    }


def test_health_and_observed_schema(client):
    assert client.get("/health").json() == {
        "status": "ok", "service": "mec-av-poc", "stored_events": 0
    }
    observed = json.loads((ROOT / "mec/baseline/openapi-observed.json").read_text())
    assert client.get("/openapi.json").json() == observed


def test_real_report_response_h3_resolution_and_listing(client, hazard):
    response = client.post("/hazards", json=hazard)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"accepted", "event"} and body["accepted"] is True
    record = body["event"]
    assert {key: record[key] for key in hazard} == hazard
    assert record["h3_cell"] == h3.latlng_to_cell(hazard["latitude"], hazard["longitude"], 10)
    assert "received_at" in record
    assert client.get("/hazards").json() == {"events": [record]}


def test_same_event_id_replaces_record_and_different_id_adds(client, hazard):
    client.post("/hazards", json=hazard)
    updated = {**hazard, "severity": 0.2, "event_type": "changed"}
    accepted = client.post("/hazards", json=updated).json()["event"]
    assert client.get("/hazards").json() == {"events": [accepted]}
    assert client.get("/health").json()["stored_events"] == 1
    assert client.post("/hazards", json={**hazard, "event_id": "second"}).status_code == 200
    assert client.get("/health").json()["stored_events"] == 2


def test_required_fields_match_live_schema(client, hazard):
    for field in hazard:
        incomplete = {key: value for key, value in hazard.items() if key != field}
        assert client.post("/hazards", json=incomplete).status_code == 422


@pytest.mark.parametrize("field,value", [
    ("latitude", 91), ("longitude", -181), ("severity", -0.1), ("severity", 1.1)
])
def test_existing_range_validation(client, hazard, field, value):
    assert client.post("/hazards", json={**hazard, field: value}).status_code == 422