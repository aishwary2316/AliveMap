# AliveMap

5G MEC autonomous-routing proof of concept using SUMO, TraCI and an existing
FastAPI/H3 service on a physical MEC server.

## Open the simulation

Double-click **Open AliveMap MEC.cmd** for your saved physical MEC connection.
The redesigned workspace opens an editable example paused, with the inspector
on the left, live map, playback timeline and a bottom tabbed console. Press Play
or Space. Vehicles, incidents and towers are edited inside the same window.
Hover icons for hints; click a vehicle in the floating legend to follow/configure
it, or Plus to add one. Origin/destination pins can be dragged onto real roads.
See the [workspace guide](docs/workspace.md) for all controls and current limits.

**Open AliveMap Playground.cmd** selects the local backend in the same workspace.
**Open AliveMap Maps.cmd** opens geographic comparisons. Select Delhi, Gujarat or
Manipur (Mantripukhri / Mayangkhang). In Settings select Streets/Terrain and MEC.
The bottom scenario icons run the seeded baseline or selected-incident case;
New and Example open editable worlds. Backend changes apply on the next load.
Legacy grid/lab launchers remain available for earlier experiments.

## Current verified status

The independent authenticated endpoint is **https://alivemap.aishtrex.com**.
No laptop SSH forwarding or Ubuntu jump VM is required for simulation. Its API,
tunnel and baseline availability supervisor are enabled for boot; API crash
recovery and saved incident recovery were tested without rebooting the host.
The existing Cloudflare applications/configuration remain unchanged. Credentials
stay in ignored private files. Browser requests without a key correctly get401.
See the [deployment guide](docs/permanent-deployment.md).

Real SUMO runs on OSM-derived directed networks. Vehicles perceive synthetic
anomalies and send reports to physical MEC; MEC computes H3 and tower-scoped
semantic delivery; each vehicle independently computes its own route. The
physical Delhi test passed 15 checks, including a driven detour, offline exclusion,
multiple incidents, selected clearance and buffering outside tower coverage.
See [HTTPS evidence](evidence/deployment/workspace-https-verification.json).
Towers and application fan-out are simulated; RF/UE/UPF transport is not verified.

The paced-telemetry controller measured 11.59x the old per-step-telemetry throughput
in one comparable 40-simulated-second headless HTTPS sample. This is not a 100x
playback or GPU benchmark. See [benchmark](evidence/deployment/playback-benchmark.json).
The full local regression run passed 67 tests; workspace integration is additionally
tested with real Tk and SUMO. [Editing details](docs/playground.md) and
[map build runbook](docs/map-system.md) cover reproducible setup. Large map assets
are excluded from Git and must be rebuilt on a different laptop.

## Layout

- mec/baseline/: reviewed original API, observed schema and dependencies.
- mec/semantic_view.py: additive read-only semantic API.
- laptop/: active SUMO controller, real MEC client, grid and self-test.
- tests/: contract, client, mapping, routing, revision and failure checks.
- evidence/: separate local and physical-MEC run results.
- docs/environment.md: verified environment and remaining discovery.
- docs/mec-api-contract.md: real endpoints, payloads, H3 and update behavior.
- scripts/mec-inventory.sh: read-only initial discovery.
- experiments/standalone-poc/: previous experiment, retained for review.
- .local/ (ignored): SSH access configuration and private discovery output.

## Local baseline verification

Use a separate Python environment (physical server Python: 3.10.12; local
verification Python: 3.12). From the repository root:

    python -m pip install -r requirements-dev.txt
    python -m pytest tests -q

The local suite exercises the observed application library versions. These tests
do not contact the physical MEC. The separate physical-MEC run is recorded in evidence/.

For the full laptop environment, install requirements-laptop.txt and run:

    python -m laptop.selftest

With the existing SSH forward kept open:

    python -m laptop.controller --mec-url http://127.0.0.1:18765 --mode physical-mec --output runs/my-run

This repository is public. Credentials, private access details and raw server
output are excluded.
