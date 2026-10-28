# Earlier standalone experiment: pending environment review

This preserves code written before inspecting the physical MEC and original API.
It is retained for review, not promoted to the actual application or deployment.

The API here is an independent new application. It does not represent or
synchronize with the existing MEC API. The network is a fictional projected grid,
not an IIIT campus map.

## Contents

- network.py: deterministic grid, directed-lane mapping and graph routing.
- controller.py: separate per-vehicle planning and TraCI route application.
- mec_api.py: experimental standalone FastAPI/SQLite/H3 service.
- test_system.py: API, mapping, routing and retry tests.
- selftest.py: real local HTTP service plus actual SUMO acceptance run.
- scenario/: generated network and inputs.

## Local reproduction only

From this directory, create and activate a Python 3.10-3.12 environment, then:

    python -m pip install -r requirements-laptop.txt
    python selftest.py --output runs/local-test

On Windows use .venv\Scripts\python.exe directly if activation is inconvenient.
The self-test starts its own local API and SUMO; it does not contact the MEC.

Previous local result: ten tests and eleven scenario checks passed. All three
vehicles arrived and both affected vehicles physically drove computed detours.
Physical-MEC integration remains unverified.