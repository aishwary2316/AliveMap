# AliveMap

5G MEC autonomous-routing proof of concept using SUMO, TraCI and an existing
FastAPI/H3 service on a physical MEC server.

## See and control it

For custom experiments, double-click **Open AliveMap Playground.cmd**. Place
vehicles on real directed roads, choose destinations/roles/profiles, draw multiple
anomalies, and place simulated 5G towers. Vehicles detect and report anomalies;
the selected MEC backend computes H3 areas and tower-scoped delivery, then each
vehicle computes its own route. Scene save/load, live connectivity, H3 overlays,
clocks and route-history inset are included. See the [playground guide](docs/playground.md)
for the full controls and local/physical/radio distinctions.
The playground extension is tested locally; its new physical-MEC endpoint must
be started and verified separately. Earlier physical-MEC results below concern
the existing guided controller, not an unverified playground deployment.

For **real geographic maps**, double-click **Open AliveMap Maps.cmd**.
Choose Delhi, Gujarat, or Manipur (Mantripukhri / Mayangkhang), then **Load / Start**.
The native AliveMap viewer now uses sharp, zoomable **OSM Streets / Terrain** maps
and visible live vehicle markers. **Play guided demo** has one button per location;
**Blue / Orange / Green** follow a vehicle and its computed route. Playback supports
**1x–100x** target speed, **Pause**, **Step**, and manual incidents. The default is an
explicit **Local demo (no SSH)** mode; choose **Physical MEC (SSH)** for real-server
messaging. SUMO runs the actual simulation behind the viewer; its own window is
optional. [Viewer controls and satellite setup](docs/map-viewer.md).

Use **Run without incident** and **Run with incident** to compare the same seeded
trips. Choose congestion, flood or closure; the selected incident starts at 20
simulated seconds and stays until **Clear incident**. A prominent simulation/wall
clock and a racing-style inset retain solid current paths and dashed old paths.
The default **Pause to inspect each route change** stops at a real routing decision;
press **Resume** to watch the vehicle drive the computed detour.

See the [Windows map-system runbook](docs/map-system.md) and
[map-stage verification](evidence/maps/verification.json). Four offline packages
were built locally from OSM, Copernicus GLO-30 and Sentinel-2. Heavy assets are
excluded from Git; the runbook gives exact rebuild commands for another laptop.

Double-click **Open AliveMap Lab.cmd** in this project folder, or run:

    python -m laptop.lab

The visible lab and native SUMO viewer open paused. Use **Play / Pause / Step**,
report **Warning / Close / Clear**, and inspect **Vehicle decisions** and the
live explanation log. Keep both SSH windows open. See the
[hands-on guide](docs/visible-lab.md) for a first experiment.

The detector events and road grid are synthetic. SUMO movement, per-vehicle route
computation, reports to the physical MEC, and semantic-view responses are live.

## Current status

The laptop controller has completed a real SUMO run against the physical MEC's
existing API through authenticated SSH forwarding. All 13 acceptance checks
passed: three arrivals, independently computed and physically driven detours,
three acknowledged semantic updates, and preservation of the original event.
There were no collisions or teleports. The new test record ended in clear state.

The physical MEC's source, schema, Python environment and launch command have
been inspected. The original application source is preserved in mec/baseline/.
Its code, environment and running process have not been changed or restarted.

See docs/mec-api-contract.md for the actual contract and its current limitations.
The launch command and working directory are verified. Automatic startup/recovery
and the 5G traffic path remain unverified.
The additive read-only semantic view is deployed on the physical MEC and its health
and manual GUI warning/closure/clear flow are verified. It reads the original
hazard store over HTTP without introducing a second store or replacing the API.
The full arrival test used the original API directly; the view's physical evidence
is a separate manual interaction test, not a second full arrival run.

See [the runnable instructions](docs/run-poc.md) and [verification evidence](evidence/verification.json).
Do not deploy the older standalone experiment as the existing MEC application.

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

All 22 local tests pass with the observed application library versions. These tests
do not contact the physical MEC. The separate physical-MEC run is recorded in evidence/.

For the full laptop environment, install requirements-laptop.txt and run:

    python -m laptop.selftest

With the existing SSH forward kept open:

    python -m laptop.controller --mec-url http://127.0.0.1:18765 --mode physical-mec --output runs/my-run

This repository is public. Credentials, private access details and raw server
output are excluded.
