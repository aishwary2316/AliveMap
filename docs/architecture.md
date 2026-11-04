# Architecture

## Responsibilities

| Layer | Modules | Processing |
| --- | --- | --- |
| Geography | `geospatial/`, `routing_core/maps.py` | OSM acquisition, SUMO conversion, projected geometry, spatial indexes, optional DSM sampling |
| Vehicle | `routing_core/agents.py` | Independent A* routes and policy-specific costs; no stored alternate routes |
| Simulation | `laptop/sumo_adapter.py` | SUMO/TraCI process, insertion, motion, validated route application |
| Scenario | `laptop/playground_session.py`, `routing_core/playground.py` | Ground truth, sensor encounters, reporting, per-vehicle knowledge and route history |
| Edge | `mec/playground_api.py` | Report validation, H3 intersection, assessment, simulated tower relevance, versions, TTL and persistence |
| UI | `laptop/map_launcher.py`, `map_canvas.py`, `playground_editor.py` | Map, controls, draft geometry, editable pins, timeline and logs |
| Transport | `laptop/playground_client.py`, `endpoint.py` | HTTPS, bearer credentials, bounded retries, endpoint validation |

`LabWorker` owns simulation and network activity off the Tk thread. The UI consumes
queued snapshots; stale frames are coalesced while logs/lifecycle events remain.
Tile downloads and local raster drawing use separate bounded worker pools.
GPU acceleration is not implemented or required by this architecture.

## A report's lifecycle

1. SUMO advances a real directed-road trip. Ground truth is a synthetic area.
2. A reporter within sensor reach creates an observation; without coverage it buffers it.
3. Telemetry associates the vehicle with a simulated circular tower. Role and
   experiment checks determine whether a report may be accepted.
4. MEC validates the report, computes intersecting H3 resolution 8/10 cells,
   records the source and assesses severity/priority/confidence. A second distinct
   scout corroborates the same incident; retries cannot create extra witnesses.
5. Relevant receiving vehicles obtain semantic facts through HTTP responses.
   This is application delivery, not RF broadcast or a cellular handover model.
6. Each vehicle computes its own route from its current road. SUMO validates the
   result. The UI retains retired path segments as dashes. If no route exists,
   the vehicle stops safely and the state is visible.

Reports include experiment/vehicle/incident IDs, version, geographic polygon,
kind and facts (such as depth or speed ratio). Telemetry includes position and
simulation time. Responses include accepted state, H3 cells, assessment and
per-vehicle deliveries. WGS84 geometry uses longitude/latitude; H3 calls use
latitude/longitude. Simulation time and wall-clock incident TTL are distinct.
See the [typed API reference](playground-api.md) for endpoints and assessment rules.

## Backend boundaries

Local mode runs the same API implementation via an in-process test client, with
the baseline bridge also local. It needs neither remote credentials nor a live
server. Persistent remote mode uses one API process and SQLite; multiple API
workers are not supported by the current experiment state design.

The original six-field baseline API remains a compatibility boundary. The
semantic-view, geographic bridge and grid controllers are retained because
existing contracts and regression tests still use them. They are not the main
desktop workflow. The superseded independent prototype is available in Git history.

Scene export stores initial placements and parameters, not a SUMO checkpoint.
Map switching creates a new scoped experiment rather than teleporting a live run.
Cleanup affects only that experiment. A failed read is an error, never an empty
incident list. Remote outages may pause simulation; automatic offline failover
would mix evidence sources and is not performed.
