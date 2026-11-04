# Geographic map packages

Run from the repository root with Python 3.12 and `requirements-laptop.txt`.
For an automated first build, use the [setup script](setup.md).
The maintained UI is `python -m laptop.map_launcher --playground`; local mode
requires no SSH connection. See [workspace controls](workspace.md).

## Build regions

```powershell
.\.venv\Scripts\python.exe -m geospatial.build delhi_urban
.\.venv\Scripts\python.exe -m geospatial.build gujarat_coastal
.\.venv\Scripts\python.exe -m geospatial.build manipur_mantripukhri
.\.venv\Scripts\python.exe -m geospatial.build manipur_mayangkhang
```

Add `--skip-rasters` for an explicitly degraded roads-only package. Streets and
local road geometry remain usable; elevation is unavailable, not fabricated.
Full builds attempt DEM and historical imagery; satellite display is optional.
No WSL, Docker or separate GDAL installation is required by the Windows wheels.

The exact footprints are in `geospatial/definitions.json`. Mayangkhang is a
regional reference, not an assertion of surveyed permanent-campus boundaries.
The automated setup uses the bundled, checksummed Delhi OSM snapshot by default;
`-RefreshMaps` requests a live extract. Direct `geospatial.build` commands use
live downloads unless supplied `--roads-snapshot assets/maps/delhi_urban.json`.
OSM acquisition uses a bounded road/restriction query with source attribution.
A failed road download aborts publication. Missing raster sources produce typed
warnings and degraded status. A failed build retains its staging data and does
not replace the last successful active package.

## Revisions and reproducibility

`map_packages/<region>/<revision>/manifest.json` records source checksums,
footprint, CRS, SUMO offset, H3 resolutions, build identity and provenance.
`active.json` selects the revision. Heavy `source/`, `processed/` and `sumo/`
folders are ignored. **Committed manifests alone cannot run a simulation.**
A new clone must build its assets; changed upstream OSM data may yield a new
revision and different scenario anchors/timings. Builds publish atomically.

Scenarios select origin/destination edges and synthetic incident geometry. The
builder discovers valid trips on the actual graph. It stores no alternate route;
vehicle planners compute routes during the run. All four regions can be selected
in the workspace; switching starts a new scoped simulation.

## Geometry and terrain

The canonical graph comes from SUMO netconvert, preserving edge IDs, original
OSM IDs/tags, lane permissions, one-way constraints and legal connections.
Geometry uses UTM 43N for Delhi/Gujarat and UTM 46N for Manipur. Network offsets
are explicitly applied. Messages use WGS84 longitude/latitude; H3 calls use
latitude/longitude. Tests check coordinate round trips and legal route validity.

H3 resolution 8/10 provides candidate indexing. Exact projected geometry
intersection determines affected roads; cell-centre membership does not decide
closures. Tests compare indexed intersections against exhaustive geometry scans.

Copernicus GLO-30 is an approximately 30 m digital surface model, including
vegetation/buildings. Sampling up to 40 m along roads and smoothing does not
make it a surveyed road grade. Nodata and implausible gradients are marked;
flood depth is a declared scenario fact, not inferred hydrodynamics. Historical
Sentinel context is nominally 10 m and cannot reliably show lane markings.

Street/terrain tiles load for the visible viewport and use a local cache. Public
services can fail; local road raster and vehicle overlays remain separate.
Do not bulk-prefetch public OSM tiles. Keep source/provider attribution visible.
See [third-party notices](../THIRD_PARTY_NOTICES.md).

## Tests and older protocols

Run `python -m pytest -m "maps and not gui" -q` after building the regions.
The current editable engine uses the typed playground API for H3 processing,
assessment and delivery. Older `laptop.map_run`/`GeoSession` commands use the
baseline compatibility envelope and remain diagnostic paths; they are not the
recommended interactive workflow. See [architecture](architecture.md).
