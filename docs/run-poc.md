# Run the POC against the inspected MEC

The active implementation is in `laptop/`. The original physical MEC source is
preserved in `mec/baseline/`. The earlier standalone experiment is historical.

For visible, interactive exploration, start `python -m laptop.lab` or double-click
**Open AliveMap Lab.cmd**. See [the hands-on guide](visible-lab.md). The command-line
controller below is the automated acceptance runner and is headless by default.

## Verified behavior

The laptop runs SUMO and TraCI. It sends actual coordinate reports to the physical
MEC's existing `POST /hazards`, then reads its `GET /hazards` through SSH forwarding.
Each vehicle independently computes and applies a route from its current edge.
The original MEC application and its existing event remain in place.

The deterministic scenario uses a fictional 6x6 grid near Imphal, 300 m spacing,
120 directed edges, seed 42 and 0.5 s simulation steps. It is not a campus road map.
Grid nodes are projected with UTM zone 46N; all 120 lane-midpoint coordinates are
tested for round-trip matching to the correct directed edge.

No alternate routes are supplied. Dijkstra searches actual SUMO turn connections
permitted for passenger vehicles, with edge length/speed costs and per-vehicle
warning penalties. Internal-junction traversal time is not included in the cost
model. Routes are applied to individual vehicle IDs and checked by TraCI.

A stationary simulated probe reports its actual lane position. Coordinates are
matched to lane polylines within 12 m; nearly tied candidates (less than 0.5 m
separation in match distance) are rejected. H3 resolution 10 remains the server's
geographic index; H3 membership is never treated as an edge ID. A report affects
the matched direction. Real GPS requires heading and uncertainty handling beyond
this exact-coordinate POC.

| Simulation time | Report | Independent response |
| --- | --- | --- |
| 1 s | `alivemap.warning`, severity 0.7 | Cautious vehicle adds 300 x severity seconds; standard adds zero |
| 45 s | `alivemap.closed`, severity 1 | Both exclude the edge from downstream routes |
| 100 s | `alivemap.clear`, severity 0 | Both recompute from their current positions |

The cautious vehicle has already turned when the standard vehicle receives the
closure, so their computed and actually traversed detours differ. The third
vehicle uses another row. A clear need not change a route when the vehicle has
already passed its choice point. The probe is removed at clear.

## Laptop setup

The current Windows workspace already has a configured `.venv`. For a fresh
Windows checkout with Python 3.12 available:

```powershell
git clone https://github.com/aishwary2316/AliveMap.git
cd AliveMap
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-laptop.txt
.\.venv\Scripts\python.exe -m laptop.selftest
```

Ubuntu 24.04 laptop instructions (not yet executed on that boot):

```bash
git clone https://github.com/aishwary2316/AliveMap.git
cd AliveMap
sudo apt-get install python3-venv
python3 -m venv .venv-linux
source .venv-linux/bin/activate
python -m pip install -r requirements-laptop.txt
python -m laptop.selftest
```

Use separate environments across operating systems. SUMO 1.28 applications and
bindings are pinned together. The self-test uses headless SUMO; a GUI run may
require your platform's GUI libraries. No SUMO installation is needed on the MEC.

The self-test rebuilds the grid twice and checks identical fingerprints. It runs
the contract/routing tests and two real SUMO sessions against local HTTP servers:
the reviewed original API, then the read-only semantic view. It stops only its own
temporary processes. Outputs are under `runs/local-verification/`.

## Existing API forwarding and physical run

Keep the currently authenticated **AliveMap – MEC tunnel** window open. It forwards
laptop `127.0.0.1:18765` to physical-MEC `127.0.0.1:8765`.

For a fresh tunnel, substitute your private SSH connection details:

```text
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -J JUMP_USER@JUMP_HOST -L 127.0.0.1:18765:127.0.0.1:8765 MEC_USER@MEC_HOST
```

The current workspace's ignored `.local/ssh_config` already contains these values.
Do not put passwords in the command or commit access details to the public repo.

Windows, from the repository root:

```powershell
curl.exe --fail http://127.0.0.1:18765/health
.\.venv\Scripts\python.exe -m laptop.controller --mec-url http://127.0.0.1:18765 --mode physical-mec --output runs/my-physical-run
```

On Ubuntu with its environment active, use `python` in place of the Windows Python
path. To watch SUMO, append `--gui --pace 0.1`. Default pacing is 0.02 wall-clock
seconds per 0.5 s simulation step. HTTP calls also block simulation advancement.
Polling is once per simulation second. This is not a radio-latency measurement.

Require `passed: true` and all 13 checks in `summary.json`. `events.jsonl` contains
reports, server acknowledgements, H3 cells, coordinate match distances, route
decisions and actual entered edges. `tripinfo.xml` and `collisions.xml` are emitted
by SUMO. Use a new output directory to retain separate runs.

## Update and failure behavior

The existing server stores free-text event types without interpreting them. The
`alivemap.*` names above form this controller's explicit semantic protocol. Each
run's event ID contains the network fingerprint and a new UUID, isolating it from
existing records and other runs. The demo overwrites only its own event ID.

The client derives a content revision from the original semantic fields, excluding
the server receipt timestamp. Its change counter is **local to the laptop**, not
an existing MEC revision feature. Receipt-only changes do not trigger routing.
Semantic changes do. All active vehicles recompute independently at an update;
vehicles on internal junction edges defer route application until they leave it.

POST retries use the identical ID and body. The original API may update its receipt
timestamp on retry. A disconnected destination stops the simulated vehicle until
an update makes routing possible. GET failures retain the last acknowledged state
for up to ten wall-clock seconds, then abort. Missing acknowledged records abort
instead of silently treating an API restart as a clear.

On an aborted run the controller attempts a clear for its own event, even if every
acknowledgement was lost. If the network is still down, cleanup failure and the
event ID are logged. The existing API has no TTL or deletion endpoint, so an
unreachable server cannot be guaranteed to receive a clear. Successful runs leave
one cleared record per run. Pre-existing records are compared before/after the run.

The synthetic warning/closure schedule is a test detector, not an AI perception
model. Routing is a per-vehicle decision in one laptop process, not a simulation
of separate onboard computers. Only the SSH application path is demonstrated;
5G user-plane traversal remains to be measured separately.

## Additive semantic API extension

`mec/semantic_view.py` is a separate, read-only HTTP view of the **same** existing
hazard store. It has no second database and does not import or replace the original
app. It reads `/hazards` over MEC loopback and exposes:

- `GET /health`: verifies the upstream service is healthy.
- `GET /semantics?prefix=...`: prefix-scoped events plus a stable content revision.

Upstream failures return 503; they do not produce a fabricated empty snapshot.
The extension preserves the original health, report and listing endpoints. Existing
reports continue to go to port 8765. The new view binds only to loopback port 8766.

Prepare the guarded deployment artifact locally:

```powershell
.\.venv\Scripts\python.exe scripts/package_semantic_view.py
```

This writes `.local/deploy-semantic-view.sh`. It checks the existing source hash,
health and port availability before writing the new extension into a separate
versioned directory. It refuses to overwrite differing code or stop an existing
listener. It uses the already-observed Python environment without installing or
upgrading dependencies, then runs the new view in the foreground. It never restarts
the original API, changes Open5GS/MicroK8s, or changes public firewall rules.

To deploy from PowerShell using the configured private SSH aliases:

```powershell
Get-Content .local/deploy-semantic-view.sh -Raw | ssh -T -F .local/ssh_config -o ConnectTimeout=600 -o ExitOnForwardFailure=yes -L 127.0.0.1:18766:127.0.0.1:8766 alivemap-mec 'bash -s'
```

Enter both passwords and keep that window open. Then verify and run:

```powershell
curl.exe --fail http://127.0.0.1:18766/health
.\.venv\Scripts\python.exe -m laptop.controller --mec-url http://127.0.0.1:18765 --semantics-url http://127.0.0.1:18766/semantics --mode physical-mec --output runs/physical-with-view
```

Keep both SSH windows open for testing. To stop the view, identify its listener on
the MEC with `ss -ltnp 'sport = :8766'`, inspect that PID's command with
`ps -p VIEW_PID -o args=`, and send `kill -TERM VIEW_PID` only after confirming it
is the new `semantic_view:create_app` process. Do not stop the old 8765 process.
Disconnecting a noninteractive SSH client is not used as a shutdown guarantee.
Persistent service management can follow after this foreground
integration is verified. See `evidence/` and the repository status for which physical
runs have actually completed; local validation does not imply physical deployment.
