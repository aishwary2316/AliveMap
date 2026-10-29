# Editable simulation playground

Double-click **Open AliveMap Playground.cmd**. The normal Maps launcher also has
**Open playground tools…**. Choose the map/subregion and backend in the main
window before opening an **Empty playground** or **Load example**. Both start
paused. All four existing OSM packages are supported. Street/terrain tiles remain
the background; SUMO supplies the actual positions and directed roads.

## Build your own scenario

1. Open an empty playground. Pick a vehicle ID, role and routing profile.
2. Click **Pick origin**, then a real road in the main map. Do the same for
   **Pick destination**. Nearby directed road IDs are offered in the direction
   selectors. The clicked origin is projected onto the road and its position in
   metres is shown. Points more than 50 m from an eligible road are rejected.
3. Click **Add / update**. A queued grey vehicle waits for safe SUMO insertion;
   **Resume** or **Step** allows it to enter. Use the vehicle dropdown and
   **Track** to follow any custom vehicle and inspect its remaining route.
4. Change a selected vehicle's role, profile or destination and **Add / update**
   again. Existing vehicles keep their actual positions. To relocate, remove
   and add a new ID. IDs cannot be reused until Reset. Unreachable directed
   origins/destinations are rejected, rather than inventing a route.
5. Give each anomaly its own ID. Choose **congestion**, **flood**, or **landslide**.
   Draw a **Circle** (one click + radius), **Rectangle** (two opposite corners),
   or **Polygon** (click vertices, then **Finish shape**). **Cancel drawing**
   returns to panning. Set flood depth, congestion speed ratio, lifetime and
   sensor range, then **Add / update anomaly**. Shapes must intersect a real
   eligible road, lie inside the extract and be valid without self-intersections.
6. Place a simulated tower with **Pick tower position**, set its coverage radius,
   then **Add / update**. Multiple towers and anomalies are supported.
7. **Resume**, pause, step, or choose 1x–100x target speed. Wall and simulation
   clocks show the actual rate. The default pause-on-route-change is useful for
   inspection; uncheck it for continuous playback.
8. **Save scene…** preserves initial placements, roles, profiles, areas and
   towers. **Load scene…** checks the exact map revision and starts a new isolated
   experiment. Reset replays the edited starting configuration. Saved scenes
   reset report versions/clearance so their anomalies can be encountered again.

Edits pause simulation time. Validation errors are shown without marking a
healthy backend disconnected. Limits: 64 vehicles, 32 towers, 32 anomaly IDs per
run (including cleared incident history on MEC), area 1 m²–25 km², at most 129
polygon vertices, tower radius 50–10,000 m, sensor range 0–100 m. At most 4,000
affected resolution-10 cells are accepted per incident.

## Roles and incident lifecycle

**reporter** senses and uploads; **receiver** listens; **both** does both;
**offline** has neither perception nor radio reception. Routing policy is a
separate choice: time_sensitive, distance_focused, low_clearance, high_clearance.
Profiles express travel-time/risk/grade costs; distance_focused is a low congestion
penalty profile, not a pure shortest-distance objective.

An amber dashed area is synthetic **ground truth**, initially unknown to agents.
A reporting vehicle within the configured sensor radius of that actual polygon
gets a local perception fact. There is no camera/LiDAR inference in this POC.
It uploads from its actual TraCI location when associated with a simulated tower;
otherwise its own report remains buffered while it is active. A receiver cannot
report. An offline vehicle never receives new facts.

The MEC extension validates experiment, geometry, role, current telemetry and
incident version. It computes overlapping H3 cells at resolutions **8 and 10**
and submits the six-field report to the **existing hazard API**. Only an actual
acknowledgement produces an active incident. The receipt's H3 cell refers to the
reporting vehicle; the affected area can cover several other cells.

MEC associates each active vehicle with the nearest tower whose circular radius
covers it. Receivers get incidents whose affected microcells overlap their
serving tower's coverage (a conservative cell-radius margin is used). Returning
to coverage delivers the current active/clear/expired state. MEC remembers each
vehicle's previously delivered incident IDs, so corrections and clearance also
reach it through a different serving tower after handover or geometry edits. New
recipients still require geographic relevance. Each vehicle retains
only its own received or locally sensed observations and independently runs A*
over the real network. Local maps, turn permissions and risk profiles determine
the route; the MEC does not send a hardcoded alternate path.

**Publish operator incident** deliberately bypasses perception, is labelled
synthetic_scenario, and still requires MEC acknowledgement. **Clear selected**
increments only that incident's version; other incidents remain active. Removing
an acknowledged anomaly clears it first. Updating one leaves the previous MEC
version in force until the new geometry/type is detected or explicitly published.
TTL is measured in **wall-clock seconds**, so speeding the simulator does not
silently change the service's expiration semantics. Expiry removes routing facts;
a persistent ground-truth anomaly needs an updated report/version to be renewed.

The live tools panel and event log show detection, upload acknowledgement, H3
counts, serving towers, recipient deliveries and each vehicle's known incidents.
Grey outlines are a local H3 display grid; **red affected cells are returned by
MEC**. At zoom 15+ the grid is r10, otherwise r8. Towers and H3 overlays can be
hidden. The racing inset uses solid current routes and dashes only abandoned
contiguous road sections, excluding portions still in the current route. A
blocked vehicle has no feasible intended path and is stopped; it is not counted
as a successful detour.

These are semantic/routing experiments. Areas do not model flood hydrodynamics,
physical debris, crash mechanics or actual radio propagation. An unaware vehicle
can drive through an anomaly; SUMO road speeds are not globally rewritten by a
semantic report. A reporting vehicle may already be past a route-choice junction
when it detects an anomaly, so a detour is not guaranteed. Mayangkhang can
legitimately have no alternate path. Arrival/retained/no-route outcomes are shown.

## Local and physical backends

**Local demo** runs the same typed MEC extension against a TestClient for the
preserved baseline API on the laptop. It needs no SSH and is explicitly labelled
local. H3 and delivery decisions execute in that backend, not the canvas.

**Physical MEC** needs the additive `mec/playground_api.py` service on loopback
8767, forwarded to laptop 18767. It uses the existing FastAPI/Pydantic/H3
environment and bridges to loopback8765. The original source, environment and
existing live processes are preserved. The existing read-only view on8766 is
independent. The new service is an in-memory research process, not a persistent
production service; restart makes old experiments invalid and pauses clients.

To prepare a guarded deployment, run:

    .\.venv\Scripts\python.exe scripts\package_playground.py

With the existing private `.local/ssh_config` host alias in place, the complete
Windows password-entry/deployment/forwarding command is:

    powershell -ExecutionPolicy Bypass -File scripts\Start-PlaygroundMec.ps1

Optional `-SshConfig`, `-HostAlias` and `-LocalPort` parameters select another
private SSH configuration/alias or local port. If the local port changes, launch
the viewer with `--playground-url http://127.0.0.1:PORT`.

If deployment reports connection refused on the original API's port8765, use:

    powershell -ExecutionPolicy Bypass -File scripts\Start-PlaygroundMec.ps1 -RecoverBaseline

Recovery first checks the reviewed source hash. Under a startup lock it leaves a
healthy API running, refuses to duplicate an existing baseline process or replace
an occupied listener, and starts the unchanged baseline with its existing Python
environment only when absent. It checks health before continuing. Its detached
process logs to `~/alivemap-playground/runtime/baseline-recovery.log`; this does
not configure automatic startup after a server reboot. The original in-memory
event store cannot be restored from a process that has already exited. Recovery
does not install packages, edit the original source, stop processes, or change
the existing 5G applications.

This writes ignored `.local/deploy-playground.sh`. Pipe that script through the
existing password-authenticated SSH configuration, forwarding18767→8767, as in
the local `.local/deploy-playground.ps1` helper. The script checks the reviewed
original source hash, original health, dependencies and free extension port. It
places a content-addressed copy in its own directory and starts foreground
Uvicorn on loopback. It stops on conflicts and never kills an existing listener.
Keep the SSH window open. No private addresses or passwords belong in Git.

The Windows launcher explicitly reads UTF-8 before piping to SSH. Windows
PowerShell's default ANSI decoding can corrupt Unicode source text and fail the
remote checksum. The corrected uploader uses a fresh `-utf8` extension directory
so an earlier failed copy is preserved instead of overwritten. A Windows native
pipe regression test verifies that the uploaded Python bytes match exactly.

Tower association and tower-scoped application fan-out are **simulated**. The
transport is HTTP polling, including over SSH for physical mode. This is not RF
broadcast or verified UE/gNB/UPF traffic. No existing 5G application is changed.
On normal close, only this run's bridged events are marked clear; unrelated MEC
events are preserved. Network failure during cleanup is an error, never a claim
that remote records were cleared.

## Verification

    .\.venv\Scripts\python.exe -m pytest tests -q --basetemp=.local/pytest-playground

`tests/test_playground.py` exercises real SUMO, real OSM road mapping, actual
sensor proximity, typed MEC processing, the preserved hazard API, per-vehicle
knowledge, driven detours, role/coverage exclusion, multiple incidents, selected
clearance, expiry, scoped cleanup, dynamic edits and circle/rectangle/polygon
conversion. These local tests do not count as physical-MEC or RF verification.

With the physical playground SSH window open, run the separate real-server check:

    .\.venv\Scripts\python.exe -u -m scripts.verify_physical_playground

This uses the Delhi fixture and the real physical endpoint, verifies perception,
legacy API acknowledgement, H3, offline exclusion, driven detours, all arrivals,
multiple incidents, selected clearance and buffered reporting after coverage
returns. After initial delivery it polls every ten simulation seconds while the
vehicles drive using their received caches; the fixture does not change incidents
during that phase. It clears its own records and closes its test experiments.
Aggregate evidence goes to `evidence/playground/physical-verification.json` and
raw run logs remain under ignored `runs/physical-playground`. This still does
not verify an RF/UE/UPF path.
