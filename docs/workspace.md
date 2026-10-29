# Single-window simulation workspace

The current shell uses a compact dark theme inspired by VS Code: charcoal panels,
flat tabs and controls, a narrow inspector, and a dark route overview. Icons are
drawn from a consistent local line-icon set; buttons do not rely on Unicode
glyphs or emoji fonts. Icon-only buttons have explicit compact widths.

The Logs tab has aligned simulation timestamps and coloured event labels:
acknowledgements in green, received updates in blue, routing decisions in purple,
warnings/inspection pauses in yellow and errors in red. Use the category selector
and search field to filter records; matches are highlighted. Follow controls
automatic scrolling and turns off when you scroll manually. The trash icon only
clears the local log view. The console retains at most 1,500 events and trims old
rows incrementally to avoid repeated large redraws.

Forms use aligned label columns, compact ID selectors and tooltip hints. Long
context text is shortened with an ellipsis; full details remain on hover. The
scenario column follows the inspector width when the divider is dragged. The
small route overview shows the followed vehicle count and total reroutes so
large fleets do not clip the summary line.


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
- **Bottom left:** visible Backend selector, map, region, With/Without incident
  selector and incident type. **Run** loads and plays the selected story;
  **Baseline** runs identical trips without the anomaly. The other two icons
  open an empty playground or a paused example. All use the same editable engine.
- **Bottom console:** Logs, Status, Current state and Settings. Logs are bounded
  and scrollable. Status contains actual/target speed and comparison results.
  Current state contains the followed vehicle's road, OSM IDs, decision and
  remaining elevation profile. Settings also selects the backend and background layer.
  Backend changes apply on the next load.
- **Header:** simulation/wall clocks and a small connection light. Green is a
  successful backend response; red is a failed connection; amber is loading.
  Local mode is labelled LOCAL. Hover for the endpoint/error; click to reconnect.

Both splitters are draggable. Pane sizing is initialized after the window is
mapped so a delayed/hidden launch cannot accidentally collapse the map. Hints
appear on buttons and form fields. No GPU driver settings or OS power settings
are changed.

The workspace adapts to 16:9 and 16:10 windows. The inspector reserves enough
width for its forms, the bottom panel sizes to its controls, and the map takes
the remaining space. The log search moves to a second row when needed. Help
text wraps, long region names use an ellipsis with a full-text hint, and the
route overview stays inside the map. Splitter choices are retained during
resizing within usable limits for the current session.

`tests/test_responsive_workspace.py` checks real Tk widget geometry at ten
viewport/text-scale combinations, including 1920x1080, 1920x1200, 1280x720,
1280x800 and a 1024x640 effective viewport. It also exercises repeated resizing,
every inspector tab, Settings, the log toolbar and splitter retention, with
text enlarged up to 150%. These are window geometry and simulated text-scaling
checks; moving the running window between physical monitors with different DPI
settings still needs a manual check on that monitor pair.

## Place and edit

1. Load Example or create New in the left inspector.
2. Click the fleet plus, enter the vehicle role/profile, then **A Origin** and
   click a road. Do the same with **B Destination**. The A/B pins can be dragged
   afterwards; dropping them snaps to real roads. Use the direction selectors
   to choose among nearby directed edges. Save the vehicle to apply the form.
3. Changing an existing vehicle's destination, role or profile keeps its real
   position. Saving a new origin/position explicitly relocates it: the old
   driving segment ends, a manual-placement event is logged, and SUMO queues
   safe reinsertion at the chosen road on the next step. A placement within
   10 m of another active vehicle is rejected visibly.
4. In Incidents, draw a circle, rectangle or polygon, set type/parameters and
   Save area. **Publish** is explicit operator injection; otherwise a reporter
   must encounter it. Clear affects the selected incident only.
5. In Towers, Place a tower, set coverage and Save. Radio shows actual MEC
   acknowledgements and per-vehicle knowledge within the simulated coverage model.

Edits pause playback. Scene files retain initial placements, not a running
checkpoint. Restart resets this run and its scoped MEC experiment; it is not
backward playback. A maintained baseline and a new active experiment are distinct.

## Stories and incidents

Run with an incident creates two sensor-only scouts and independently routing
receivers. Each scout physically approaches the anomaly and uploads its own
observation. The selected MEC backend computes overlapping H3 cells and a
transparent risk assessment: closure severity 1, flood depth/0.5 m capped at 1,
congestion 1-speed ratio. It reports priority and marks two distinct sensor
reporters as corroborated. Operator publication is explicitly labelled injection
and does not count as an independent sensor reporter. This is a deterministic
POC policy, not a calibrated safety assessment.

Tower-scoped delivery informs receivers, which compute their own routes on the
real directed graph. Both the main map and the route overview show withdrawn
route segments dashed and current paths solid. When a closure leaves no route,
the vehicle stops and the story says so; Mayangkhang's closure can legitimately
produce a safe stop instead of a detour. No alternative road is invented.

The same trips without incidents form the baseline. Completed run arrival times
remain available in Status. **Run** disables inspection pauses so the story can
continue to the second scout; you can enable Pause on reroute for step-by-step
inspection. A paused Example respects that checkbox. The on-map notice explains
drawing, load errors and story progress. Editing a story turns it into a custom
playground instead of continuing a scripted narration about manually changed data.

For a custom incident, enter a new ID, select Circle/Rect/Polygon, and click the
map (one centre/two corners/three or more polygon vertices). Finish closes a
polygon. The orange dashed preview is **unsaved**. Save area creates ground
truth; a reporting vehicle must discover it. Publish injects that saved incident
immediately, with a MEC acknowledgement. Clear sends a versioned clearance and
disables detection; the trash removes the saved object. Cancel discards the
draft without removing an existing incident. Edit successes and errors are logged.

A physical connection failure cannot prevent starting a new Local run, even if
cleanup of the previous physical experiment fails. The retained remote experiment
is reported for later cleanup; it is never silently erased. Local mode executes
the same H3/assessment/delivery API inside the laptop, with no SSH or Internet
requirement for SUMO or the packaged road network. Internet is only needed for
uncached decorative background tiles in that mode.

The physical API must advertise `story_revision: 1`. A guarded API-only update is
available through `scripts/Update-PlaygroundMec.ps1`, using the ignored SSH
configuration and original private deployment record. It verifies source hashes,
preserves SQLite experiments, updates only the managed API, checks readiness,
and rolls back on failure. It does not edit the original API, tunnels, DNS,
firewall, Open5GS, MicroK8s or radio configuration.

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
frames are coalesced per run, while all log/lifecycle events retain order. Snapshot files
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

### Map interaction performance

Map paints are now coalesced on a 16 ms timer. Background requests have four
active download slots and no FIFO backlog of old views; each completion chooses
tiles from the current viewport, starting near the center. Socket timeouts are
four seconds. Cache reads and image decoding happen on those workers. An
interrupted/corrupt cache is refetched. Already downloaded parent imagery can
serve as a temporary zoom preview until the requested sharp tiles arrive.

Two separate workers rasterize the actual local OSM/SUMO roads and the display
H3 grid into reusable tiles. This keeps road geometry usable during imagery
outages, including partially loaded views, and avoids rebuilding thousands of
native drawing objects on each drag. The red affected H3 cells still come from
the selected MEC backend. Native image uploads have an 8 ms scheduling budget
per paint (a single native operation may exceed it); additional uploads are
spread across paints. Hidden elevation plots are not rebuilt, and unchanged
route profiles are reused. None of these display changes skip SUMO steps or
replace per-vehicle routing.

MEC reads/idempotent playground operations have one short retry, with a 3 s
read/write timeout and a 2 s connect timeout. A failed MEC still pauses physical
playback and requires reconnecting; local demo is an explicit mode. A Cloudflare
530 response was independently observed during this performance work. No remote
service, tunnel or DNS configuration was changed to conceal that outage.

`tests/test_map_responsiveness.py` holds all four imagery requests open while
exercising input, verifies that obsolete views are not subsequently downloaded,
and checks UI heartbeat, bounded work and raster H3 output. The existing UI,
editor, routing and four-map worker regressions were also run. Measured native
rendering results are in `evidence/deployment/map-ui-benchmark.json`. The test
uses Delhi at a 1600x900 viewport with network disabled and cached raster data;
it isolates interaction/painting and does not measure Internet download speed,
initial map preparation, physical MEC throughput or a real 5G radio path.

To reproduce, first save the baseline module and then use an existing playground
run snapshot (both baseline source and snapshots stay ignored):

```powershell
git show 6a3569c:laptop/map_canvas.py | Set-Content -Encoding utf8 .local/map_canvas_before.py
.\.venv\Scripts\python.exe -m scripts.benchmark_map_ui --baseline-source .local/map_canvas_before.py --snapshot runs/<run>/current.json
```

`tests/test_desktop_workspace.py` exercises real Tk/SUMO: docked tabs, mapped pane
sizes, pin hit/drag/drop, tile-item reuse, custom vehicle, role, keyboard focus,
play/pause/step and map switching. Existing engine/editor tests cover shapes,
towers, multiple incidents, clearance, save/load and independently driven routes.
Physical integration and local tests are recorded separately. Tower coverage
remains synthetic; an actual radio/UE/UPF path is not verified by these tests.
