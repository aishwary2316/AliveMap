# AliveMap

5G MEC autonomous-routing proof of concept using SUMO, TraCI and an existing
FastAPI/H3 service on a physical MEC server.

## Current status

The physical MEC has now been accessed over password-authenticated SSH. Its
OS, Python environment, running API schema and POC source have been inspected.
The reviewed original source and observed dependency versions are preserved in
mec/baseline/. No remote application has been modified.

See docs/mec-api-contract.md for the actual contract and its current limitations.
The startup/lifecycle configuration and 5G traffic path remain unverified.
Do not deploy the older standalone experiment as the existing MEC application.

## Layout

- mec/baseline/: reviewed original API, observed schema and dependencies.
- tests/: local compatibility checks for the real API contract.
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

All eight compatibility tests passed locally with the observed library versions. These tests run the reviewed source locally and do not contact the MEC.

This repository is public. Credentials, private access details and raw server
output are excluded.