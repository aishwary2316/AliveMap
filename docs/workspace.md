# Single-window simulation workspace

Double-click **Open AliveMap MEC.cmd** for the saved physical HTTPS connection.
It opens the selected map's editable example in the background, paused. Press
the triangle below the map or Space to run. **Open AliveMap Playground.cmd**
opens the same workspace with the local backend selected. No extra editor window
is created. Existing map packages, scene files, SUMO and the MEC API are reused.

## Layout and controls

- **Left inspector:** Vehicles, Incidents, Towers and Radio tabs. New, Example,
  Open and Save apply to the whole scene. Each tab scrolls independently.
- **Map:** the largest pane. Drag to pan; wheel to zoom. The floating fleet
  legend expands on hover over its heading; click its heading to collapse it.
  Click a coloured vehicle to follow it and load its form. Its gear opens the
  vehicle tab. Plus starts a new vehicle form with an unused ID.
- **Below the map:** restart, play/pause, single step, faster and the target-rate
  selector. Space toggles playback; Right advances one step. Shortcuts do not
  intercept typing in forms or the log. The timeline shows elapsed simulation
  time and route-change markers; it does not claim reversible time travel.
- **Bottom left:** map, subregion and guided-comparison incident. Hover the
  four action icons for baseline, incident run, empty playground and example.
- **Bottom console:** Logs, Status, Current state and Settings. Logs are bounded
  and scrollable. Status contains actual/target speed and comparison results.
  Current state contains the followed vehicle's road, OSM IDs, decision and
  remaining elevation profile. Settings selects the backend and background layer.
  Backend changes apply on the next load.
- **Header:** simulation/wall clocks and a small connection light. Green is a
  successful backend response; red is a failed connection; amber is loading.
  Local mode is labelled LOCAL. Hover for the endpoint/error; click to reconnect.

Both splitters are draggable. Pane sizing is initialized after the window is
mapped so a delayed/hidden launch cannot accidentally collapse the map. Hints
appear on buttons and form fields. No GPU driver settings or OS power settings
are changed.

## Place and edit

1. Load Example or create New in the left inspector.
2. Click the fleet plus, enter the vehicle role/profile, then **A Origin** and
   click a road. Do the same with **B Destination**. The A/B pins can be dragged
   afterwards; dropping them snaps to real roads. Use the direction selectors
   to choose among nearby directed edges. Save the vehicle to apply the form.
3. Changing an existing vehicle's destination, role or profile keeps its real
   position. Relocation still requires removing it and creating a new ID; an
   invalid origin change produces a visible error instead of moving it secretly.
4. In Incidents, draw a circle, rectangle or polygon, set type/parameters and
   Save area. **Publish** is explicit operator injection; otherwise a reporter
   must encounter it. Clear affects the selected incident only.
5. In Towers, Place a tower, set coverage and Save. Radio shows actual MEC
   acknowledgements and per-vehicle knowledge within the simulated coverage model.

Edits pause playback. Scene files retain initial placements, not a running
checkpoint. Restart resets this run and its scoped MEC experiment; it is not
backward playback. A maintained baseline and a new active experiment are distinct.

## Performance and verification

The physical controller previously waited for HTTPS on every 0.5-second SUMO
step. It now sends routine telemetry at most every 250 ms of real time, with
immediate updates on predicted coverage/serving-tower changes and before an
observation upload. Prediction only triggers a request: MEC still authorizes
coverage, H3 and delivery. Perception and movement execute every SUMO step.
Incoming external updates are observed on the next sample; the remaining real
network delay still applies. Local mode retains per-step deterministic telemetry.

Repeated TraCI state reads are cached within a step and invalidated by movement
or route changes. Tile items, H3 boundaries/covers and sensor polygons are reused.
Very broad display grids are omitted rather than allocating thousands of cells;
zoom in to inspect them. Authoritative affected cells remain visible. Adjacent UI
frames are coalesced, while all log/lifecycle events retain order. Snapshot files
are written once a second during playback instead of on every tick.

The reproducible physical HTTPS benchmark is:

    .\.venv\Scripts\python.exe -m scripts.benchmark_playback --url https://alivemap.aishtrex.com

The recorded Delhi sample advanced 40 simulated seconds in 27.152 s with per-step
telemetry versus 2.349 s with paced telemetry: 11.59x relative throughput, with
80 versus 4 telemetry requests and no collisions/teleports. It excludes map load
and UI rendering, has no anomalies, and is not a guarantee of 100x playback or
an FPS/GPU benchmark. See `evidence/deployment/playback-benchmark.json`.

The laptop's inspected hardware is Ryzen 7 7735HS (8 cores/16 threads), integrated
Radeon and RTX 3050 6GB. Network waits cannot be solved with extra GPU usage.
SUMO still runs its native process, UI and simulation use separate threads, and
map downloads use the existing bounded thread pool. No claim of GPU acceleration
or saturating all cores is made.

`tests/test_desktop_workspace.py` exercises real Tk/SUMO: docked tabs, mapped pane
sizes, pin hit/drag/drop, tile-item reuse, custom vehicle, role, keyboard focus,
play/pause/step and map switching. Existing engine/editor tests cover shapes,
towers, multiple incidents, clearance, save/load and independently driven routes.
Physical integration and local tests are recorded separately. Tower coverage
remains synthetic; an actual radio/UE/UPF path is not verified by these tests.
