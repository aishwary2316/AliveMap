# Real geographic map system: Windows runbook

**Viewer update:** use [the geographic viewer guide](map-viewer.md) for the current
sharp street/terrain display, vehicle tracking, guided demos and speed controls.
Local demo is now the explicit default; select Physical MEC for SSH integration.
The native SUMO window and the older steps below remain available for diagnostics.

Run commands from the AliveMap repository directory in PowerShell. The existing
grid lab, original MEC API and read-only semantic view are preserved.

## See and control the simulation

1. Keep the existing password-authenticated MEC SSH tunnel open. Its local
   endpoint is `http://127.0.0.1:18765`. Private SSH settings stay in `.local/`.
2. Double-click **Open AliveMap Maps.cmd**, or run:

   ```powershell
   .\.venv\Scripts\python.exe -m laptop.map_launcher
   ```

3. Select **Delhi Urban**, **Gujarat Coast**, or **Manipur Hills**. Manipur has
   separate **manipur_mantripukhri** and **manipur_mayangkhang** subregions.
4. Select its scenario and click **Load / Start**. This starts a fresh experiment,
   including its scheduled synthetic incident. SUMO is the primary map viewer.
   Colored lines show independently computed routes: blue cautious, orange
   standard, green unaffected. Red polygons show the current synthetic incident.
   Line thickness is a visibility aid, not a road-width measurement.
5. **Pause / Step / Resume** control movement. **Report incident / Close road /
   Clear incident** send real reports to MEC without advancing a paused simulation.
   A manual report disables the automatic timeline for that run.
6. **Reset** clears this run's own event and starts the same scenario paused.
   Select another map and **Load / Start** to switch. Loading is a controlled
   restart, not a geographic teleport. **Reconnect** retries MEC after an outage.

The status reports the active map/scenario, experiment UUID, simulated time,
MEC reachability and last error. A failed MEC read pauses the controller; it is
never interpreted as an empty hazard map. Do not start movement using SUMO's own
toolbar: the AliveMap controller owns TraCI stepping. Existing grid controls are
still under **Open AliveMap Lab.cmd**.

## Installation and reproducible source builds

Existing tested environment: native Windows 11, Python 3.12, SUMO 1.28.0 wheels.
No WSL, Docker, QGIS or separately installed GDAL is required.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-laptop.txt
.\.venv\Scripts\python.exe -m geospatial.build delhi_urban
.\.venv\Scripts\python.exe -m geospatial.build gujarat_coastal
.\.venv\Scripts\python.exe -m geospatial.build manipur_mantripukhri
.\.venv\Scripts\python.exe -m geospatial.build manipur_mayangkhang
```

Definitions and precise WGS84 footprints are in `geospatial/definitions.json`.
Mayangkhang uses the village/permanent-campus region as a geographic reference;
the exact permanent-campus boundary has not been surveyed or asserted. The city
campus reference is supported by OSM campus-road features. Both extracts extend
northward; their terrain attributes come from the actual raster, not a fictional
hill surface.

Public source services can time out. Failed builds retain their staging data and
do not replace an active package. Retry the command after a source outage. An OSM
failure aborts publication; unavailable DEM/imagery produces a typed
`SOURCE_UNAVAILABLE` warning and an explicitly degraded package. `--skip-rasters`
is an intentional roads-only diagnostic build, never a complete package.

`map_packages/<id>/<revision>/manifest.json` pins source-file checksums, footprint,
CRS, SUMO offset, H3 version/resolutions, build ID and provenance. `active.json`
selects the successful revision. Raw sources, large graph/raster/SUMO artifacts
and staging folders are ignored by Git. **A fresh clone must build assets**;
committed manifests alone cannot run a simulation. The selector says when a
package needs building. OSM source revisions and public imagery catalogues may
change: a new download can legitimately produce a new revision. Existing local
packages work offline for geography; MEC connectivity is still needed.

## Architecture and geographic processing

`routing_core/maps.py` implements the **MapProvider** contract. Its canonical
directed graph is exported from netconvert's SUMO network, retaining actionable
edge IDs, source OSM IDs/tags, road geometry, class permissions and legal outgoing
connections. No alternate route is stored in a scenario. Every computed route
passes graph validation and SUMO's route-validity check before use.

`routing_core/agents.py` contains **VehicleAgent** and its own A* implementation.
Each vehicle combines travel time, its congestion sensitivity, water-depth
tolerance/risk and uphill cost. Landslide polygons exclude intersecting roads;
an impossible destination returns `no feasible route` and stops the vehicle.
Profiles are deliberately simple POC policies. The `distance_focused` profile
currently means low congestion sensitivity over the travel-time base cost; it
is not a pure shortest-distance optimizer. These are not autonomous driving
safety models.

`laptop/sumo_adapter.py` is the **SimulatorAdapter**: spawn, movement, position,
coordinate conversion and route application. It contains no route optimizer.
`laptop/geo_session.py` adds **ScenarioController**, reusing the existing
LiveSession event logging and LabWorker controls. Activation validates the
package/scenario, closes the previous adapter, creates a UUID and builds fresh
agents. Queued commands carry their original epoch and are rejected after a
switch. Old MEC records are scoped out; unrelated remote records are never
globally deleted. Cleanup clears only this run's own event.

Scenarios are separate JSON inputs with OD edge references, profiles, incident
geometry and an event timeline. The builder discovers and validates a meaningful
default scenario; it stores no route sequence. For a custom scenario use
`--scenario <path>` with the experiment command below. It must reference the exact
map/build and pass the same road/geometry checks.

All transmissions use WGS84; H3 receives latitude then longitude. Delhi/Gujarat
use UTM 43N, Manipur UTM 46N; rasters retain georeferencing and are reprojected to
the same metric CRS as the road network. Raster placement adds the actual SUMO
offset. Representative preprocessing round trips must be within 1 cm; live
TraCI/provider conversions must agree within 5 cm.

H3 resolution 8 provides macro indexing (~531 m average cell-edge length), and
resolution 10 micro indexing (~76 m). Road lines are densified, neighbouring-cell
candidates collected, then exact line/cell intersection creates the index.
Hazard association uses that index followed by **exact projected geometric
intersection**, including boundary-crossing roads. Tests compare against a full
road-geometry scan. H3 centroid membership alone never decides road closure.

## MEC messages and present limitations

The physical server's original six-field `/hazards` contract is unchanged.
The geographic bridge uses an explicitly versioned `alivemap.geo.v1:` JSON
envelope inside the existing free-text `event_type` field. The envelope contains
experiment/map ID, version, observation/expiry times, source type, geographic
polygon, and semantic facts (speed ratio or water depth). The outer point is the
polygon centroid. The real server validates the outer coordinates/severity,
computes H3 resolution 10, adds receipt time, stores and acknowledges it.

**Envelope validation, version checks, geographic association and expiry are
currently enforced by the laptop bridge.** The legacy MEC does not parse the
envelope, expire records or provide durable storage. This compatibility step
requires no remote install/restart and leaves the original API and existing
semantic-view process intact. A future additive server API can enforce structured
semantics and expiry on MEC; that server-side enhancement is still pending.

The laptop polls real MEC records and feeds the same semantic facts to independent
agents. MEC supplies no route or universal road penalty. Default map runs poll
the original API; the existing read-only semantic view is optional via
`--semantics-url http://127.0.0.1:18766/semantics` when its tunnel is open.
SSH forwarding proves remote application processing. It does not prove a 5G UE
bearer, multicast, PC5, URLLC, push notifications or measured radio latency.

Congestion/flood/landslide incidents are labelled **synthetic scenarios**. They
affect routing policies; current SUMO speeds are not reduced by a calibrated
traffic model. Flood depths are declared scenario facts, not inferred from
elevation or a hydrodynamic/tsunami model.

## Sources, licences and terrain limits

- Roads: OpenStreetMap contributors, ODbL 1.0; retain attribution and applicable
  derivative-database obligations. Source extract/query/timestamp are retained.
  https://www.openstreetmap.org/copyright
- Elevation: Copernicus DEM GLO-30 Public (2021 release), approximately 30 m
  **digital surface model**, vertical EGM2008/metres. Includes buildings/vegetation;
  it is not surveyed bare-earth road grade. Source windows/metadata are retained.
  https://registry.opendata.aws/copernicus-dem/
  https://copernicus-dem-30m.s3.amazonaws.com/readme.html
- Satellite: historical 2024 Sentinel-2 L2A natural-colour visible-band context,
  nominally 10 m, acquired as permitted offline COG windows through Earth Search.
  Catalogue scene IDs, dates, scene-wide cloud cover, source URLs and licence
  references are in provenance. Cloud scores are not local cloud verification;
  mosaics can combine dates. It cannot show reliable lane markings.
  https://earth-search.aws.element84.com/v1
  https://dataspace.copernicus.eu/terms-and-conditions

Terrain samples are spaced at up to 40 m along road geometry, median-smoothed,
and marked unavailable/nodata/implausible instead of inventing elevations.
DSM-derived gradients remain approximate, especially on short urban edges and
bridges. Native Windows netconvert/GDAL heightmap capability is probed and logged;
routing uses the standalone rasterio sampling fallback even when that probe
succeeds. The probe network is diagnostic, not the active road network. OSM
turn/lane tags and netconvert signal inference also have limitations; conversion
warnings are retained for inspection.

## Run experiments and tests

```powershell
.\.venv\Scripts\python.exe -m laptop.map_run delhi_urban --gui
.\.venv\Scripts\python.exe -m laptop.map_run delhi_urban --incident-only
.\.venv\Scripts\python.exe -m laptop.map_run gujarat_coastal
.\.venv\Scripts\python.exe -m laptop.map_run manipur_mantripukhri
.\.venv\Scripts\python.exe -m laptop.map_run manipur_mayangkhang
.\.venv\Scripts\python.exe -m pytest -q --basetemp .local/pytest-maps
```

Default timeline: primary incident at t=1 s, closure at t=12 s, clear at t=100 s.
Manipur's primary incident is already a landslide closure. `--incident-only`
holds the primary incident to measure driven profile differences; a permanent
Mayangkhang closure can correctly prevent arrivals. Full runs clear it and allow
vehicles to proceed. Runs write JSONL report/acknowledgement/route logs, driven
edges, tripinfo, summaries and optional GUI screenshot under ignored `runs/maps/`.
Tests use the reviewed API locally, not the physical server. Real-map integration
tests skip when heavy assets have not been built. Physical evidence is recorded
separately in `evidence/maps/verification.json`.
