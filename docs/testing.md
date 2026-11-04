# Testing

Use Python 3.12 and install `requirements-dev.txt` from the repository root.
Runtime installations use `requirements-laptop.txt`; pytest is not a runtime dependency.

```powershell
# Portable contracts, routing, persistence, transport and deployment checks
.\.venv\Scripts\python.exe -m pytest -m "not gui and not maps" -q

# Geographic/SUMO integration after building the map assets
.\.venv\Scripts\python.exe -m pytest -m "maps and not gui" -q

# Native desktop checks: run on an unlocked interactive desktop
.\.venv\Scripts\python.exe -m pytest -m gui -q

# Complete regression campaign
.\.venv\Scripts\python.exe -m pytest -q --junitxml=runs/test-results.xml
```

On restricted Windows environments, supply a fresh writable temporary directory,
for example `--basetemp=.local/pytest-publication`. Pytest removes the chosen base
directory on a later run: never point it at useful files.

`pytest.ini` limits discovery to the maintained `tests/` suite. The collection
hook in `tests/conftest.py` assigns explicit UI/map tiers. Some integration tests
in otherwise portable modules skip if assets are absent. SUMO binaries come from
the pinned wheel; no system SUMO installation is required.

The GitHub workflow runs portable checks on Windows and Ubuntu. A workflow file
is not proof that hosted CI passed: inspect its actual run before releasing.
Desktop tests open windows and may take several minutes; public imagery is
stubbed where a deterministic rendering assertion is needed.

Keep tests that protect independent routing, geometry intersection, distinct
reporters, versioning, scoped cleanup, persistence, credentials, and UI edits.
These caught real defects. Avoid tests that merely duplicate implementation.
The superseded prototype's tests have been retired with that prototype.

## Physical MEC experiments

These are explicit operator actions, excluded from pytest and CI:

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_mec_story --output runs/physical-story
```

Requires Delhi assets and a separately configured authenticated service. The
script creates and cleans its own experiment; it still reads the shared service
and must be run only on a service you administer. Keep raw output private and
redact endpoints, identifiers and operational details before publishing results.
Do not run recovery/crash tests on shared infrastructure during ordinary CI.
