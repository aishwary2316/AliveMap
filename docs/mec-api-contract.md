# Existing MEC API contract

Directly inspected on 28 October 2026: the running service's OpenAPI schema,
the existing main.py and dependency metadata from its Python environment.
Source and schema snapshots are in mec/baseline/.

## Existing behavior

GET /health returns status, service and stored_events. The observed service
identifier is mec-av-poc.

POST /hazards requires these JSON fields:

| Field | Type | Existing validation |
| --- | --- | --- |
| event_id | string | required |
| vehicle_id | string | required |
| latitude | number | -90 to 90 |
| longitude | number | -180 to 180 |
| event_type | string | required, free text |
| severity | number | 0 to 1 |

It returns accepted: true and an event record containing those fields plus:
- h3_cell, computed from latitude/longitude at H3 resolution 10.
- received_at, a server-generated UTC ISO timestamp.

GET /hazards returns an object containing an events array, not a bare array.

An event_id identifies a dictionary entry. Submitting the same ID replaces that
entry, including its timestamp. A different ID adds another entry. State is held
in process memory; process restart loses it. The existing code has no TTL,
semantic revision, deletion endpoint, vehicle-specific query, route planner or
directed road-edge mapping. event_type is stored without interpreting it.
A value such as clear has no built-in clearing effect.

The API source defines no application authentication. Its observed listener is
loopback-only. This statement does not infer any external proxy configuration.

## Verified runtime

| Component | Observed on physical MEC |
| --- | --- |
| OS | Ubuntu 22.04.5 LTS |
| Python | 3.10.12 |
| FastAPI | 0.162.0 |
| Pydantic | 2.14.1 |
| H3 | 4.5.0 |
| Uvicorn | 0.54.0 |
| Bind | 127.0.0.1:8765 |

## Implications for the next increment

1. Keep POST /hazards and GET /hazards compatible with this contract.
2. Preserve H3 resolution 10 for existing records. H3 is a geographic index,
   not a directed SUMO edge identifier.
3. Introduce update/clear/expiration semantics explicitly; the current service
   does not provide them.
4. Match reported coordinates to the actual simulation network's lane geometry.
   Never infer a road edge from cell membership alone.
5. Keep separate routing state and route computation for every vehicle.
6. Determine the API's current launch/lifecycle before planning a restart or
   deployment. Its service-manager/startup configuration has not been inspected.
7. Confirm the actual laptop-to-MEC test path. Application health over SSH is
   not proof of a 5G user-plane path.

No runtime dependency or MEC application was changed during discovery.
Local contract tests exercise the reviewed source with observed library versions;
they do not submit test events to the physical service.