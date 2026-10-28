# AliveMap

5G MEC autonomous-routing proof of concept using SUMO, TraCI and an existing
FastAPI/H3 service on a physical MEC server.

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
The additive read-only semantic view is implemented and locally tested. Its
physical deployment remains pending. It reads the original hazard store over HTTP;
it does not introduce a second store or replace the existing API.

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

All 19 local tests pass with the observed application library versions. These tests
do not contact the physical MEC. The separate physical-MEC run is recorded in evidence/.

For the full laptop environment, install requirements-laptop.txt and run:

    python -m laptop.selftest

With the existing SSH forward kept open:

    python -m laptop.controller --mec-url http://127.0.0.1:18765 --mode physical-mec --output runs/my-run

This repository is public. Credentials, private access details and raw server
output are excluded.
