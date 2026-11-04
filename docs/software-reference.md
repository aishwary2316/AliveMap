# Software and source reference

This inventory describes the implementation in this repository. It separates
the simulation engine, geographic inputs, application code and optional edge
deployment. Version pins are defined by the requirement files, not this guide.

## Runtime software

| Component | Use in AliveMap | Source |
| --- | --- | --- |
| Python 3.12 | Tested desktop runtime; application, map processing and tests | [Python](https://www.python.org/) |
| Eclipse SUMO 1.28.0 | Microscopic vehicle movement and road-network conversion | [SUMO](https://eclipse.dev/sumo/) |
| `eclipse-sumo`, `sumo-data` | Pinned binaries and SUMO support data | `requirements-laptop.txt` |
| TraCI / sumolib 1.28.0 | Control SUMO, read networks, validate and apply routes | [SUMO tools](https://sumo.dlr.de/docs/Tools.html) |
| H3 4.5.0 | Resolution 8/10 spatial cells and geographic indexing | [H3](https://h3geo.org/) |
| Shapely 2.1.2 | Polygon validation, projected intersections and spatial indexing | [Shapely](https://shapely.readthedocs.io/) |
| pyproj 3.7.1 | WGS84 / projected-coordinate transformations | [pyproj](https://pyproj4.github.io/pyproj/) |
| rasterio 1.4.3 | Georeferenced raster windows, reprojection and terrain sampling | [rasterio](https://rasterio.readthedocs.io/) |
| NumPy 2.5.4 | Raster arrays, terrain samples and numerical processing | [NumPy](https://numpy.org/) |
| NetworkX 3.5 | Graph analysis used during scenario generation and verification | [NetworkX](https://networkx.org/) |
| Pillow 11.3.0 | Tile decoding, local road/H3 rasters and line-icon rendering | [Pillow](https://pillow.readthedocs.io/) |
| Tk / ttk | Native single-window desktop, canvas, forms and text console | Python's `tkinter` module |
| FastAPI 0.162.0 | Typed MEC HTTP application and local in-process API | [FastAPI](https://fastapi.tiangolo.com/) |
| Pydantic 2.14.1 | Validated API request models | [Pydantic](https://docs.pydantic.dev/) |
| Uvicorn 0.54.0 | Optional independently running HTTP API process | [Uvicorn](https://www.uvicorn.org/) |
| HTTPX 0.28.1 | Verified HTTPS transport and in-process API tests | [HTTPX](https://www.python-httpx.org/) |
| SQLite | Optional persistent MEC experiment state | Python's `sqlite3` module |

The vehicle planner is AliveMap's own edge-based A* implementation in
`routing_core/agents.py`. SUMO supplies vehicle movement; NetworkX does not
choose the live per-vehicle detours. See [the routing model](routing-model.md).

## Dependency files

- `requirements-mec.txt` includes the reviewed API dependency snapshot and HTTPX.
- `requirements-laptop.txt` adds simulation, geography and rendering packages.
- `requirements-dev.txt` adds pytest 8.3.5 to the laptop environment.
- `mec/baseline/requirements-observed.txt` records the original API environment.
  It includes framework/support packages such as Starlette, AnyIO, h11, click,
  idna, annotated-types/doc, typing extensions/inspection, Pydantic Core,
  exceptiongroup and OpenTelemetry API. Their presence does not imply an
  instrumented tracing pipeline; they preserve the observed environment.

Tk/Tcl availability depends on the Python installation. Windows' standard Python
installer includes the Tcl/Tk option. The laptop environment includes SUMO wheels;
a separate system SUMO, QGIS, WSL or Docker installation is not required for the
documented Windows workflow.

## Geographic inputs and services

| Input/service | Purpose and boundary |
| --- | --- |
| OpenStreetMap / Overpass | Bounded real road extracts, road tags and turn restrictions used at map-build time |
| OpenStreetMap raster tiles | Viewport street background; separate from the routing graph |
| OpenTopoMap tiles | Terrain-style background; does not replace the DEM used for road attributes |
| Copernicus DEM GLO-30 | Optional approximate elevation/grade attributes from a digital surface model |
| Earth Search / Sentinel-2 L2A COGs | Optional historical visual context during full map builds |
| Optional custom tile service | Explicit local configuration; no commercial provider is required by default |

Footprints and regional references are in `geospatial/definitions.json`.
Acquisition queries, timestamps and product metadata are recorded during builds.
Attribution and source terms are in [third-party notices](../THIRD_PARTY_NOTICES.md).
Neither public map tiles nor a downloaded image is a road-routing engine.

## Source map

| Source | Responsibility |
| --- | --- |
| `geospatial/acquisition.py` | Download roads and bounded raster subsets |
| `geospatial/build.py` | Convert roads, sample terrain, build indexes and publish a validated revision |
| `geospatial/scenarios.py` | Discover and validate scenario trips and incident anchors |
| `routing_core/maps.py` | Package validation, real directed graph, projections and spatial queries |
| `routing_core/agents.py` | Observations, vehicle profiles and independent A* |
| `routing_core/playground.py` | Scene validation, examples and two-scout stories |
| `laptop/map_launcher.py`, `lab.py` | Main desktop and background command/session worker |
| `laptop/desktop_ui.py` | Shared desktop shell, hints and fleet controls |
| `laptop/playground_session.py`, `sumo_adapter.py` | Perception, vehicle knowledge, edits and SUMO control |
| `laptop/playground_editor.py` | Vehicle/tower/incident forms, drawing and pin placement |
| `laptop/map_canvas.py`, `offline_tiles.py` | Interactive display, HTTP tile cache and local geometry rasters |
| `laptop/route_drawing.py`, `route_minimap.py` | Retired-route segments and route overview |
| `laptop/responsive.py`, `ui_theme.py`, `ui_icons.py`, `log_console.py` | Layout, styling, icons and bounded event console |
| `laptop/endpoint.py`, `playground_client.py` | Private endpoint selection, authentication and typed transport |
| `mec/playground_api.py` | H3, assessment, delivery decisions, versions and persistence |
| `deployment/`, `scripts/*PermanentMec.ps1`, `scripts/*PlaygroundMec.ps1` | Guarded operator packaging, installation, verification and updates |
| `scripts/verify_mec_story.py`, `verify_physical_playground.py` | Explicit physical-API scenario acceptance tools |
| `scripts/benchmark_map_ui.py`, `benchmark_playback.py` | Rendering and telemetry throughput comparisons |
| `tests/` | Maintained contract, geometry, routing, persistence, transport and native UI checks |
| `Setup.ps1`, `scripts/setup_local.py`, `scripts/setup_maps.py` | Local environment bootstrap, dependency checks and validated map reuse/build |
| `scripts/verify_local.py` | Real SUMO two-scout and incident-free baseline acceptance check without remote services |

Compatibility modules remain deliberately separate: `laptop/controller.py`,
`live_session.py`, `network.py` and `selftest.py` cover the deterministic grid;
`geo_session.py`, `geo_mec.py` and `map_run.py` cover the earlier geographic
protocol. `mec/baseline/` preserves the reviewed original application, and
`mec/semantic_view.py` its read-only extension. `mec/baseline_watch.py` supervises
only the reviewed baseline. They are not alternative production architectures.

## Operational tools

Git tracks source and manifests. PowerShell launchers support native Windows
operation; OpenSSH is used only for administration or optional legacy forwarding.
Managed remote deployment uses Linux systemd and an independent Cloudflare
Tunnel connector. These are optional infrastructure components, not required
by local simulation. GitHub Actions configures portable checks on Windows and
Ubuntu; its actual results must be checked separately from local evidence.

GPU compute, physical sensor drivers, RF propagation simulation and 5G core/RAN
control are outside the current runtime.
