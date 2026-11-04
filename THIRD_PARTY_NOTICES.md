# Licensing and third-party materials

## Geographic data and tiles

| Material | Attribution / terms |
| --- | --- |
| OSM roads and derived databases | Â© OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright). Preserve attribution and applicable derivative-database/share-alike obligations. |
| OSM raster street tiles | OpenStreetMap contributors; follow the separate [tile usage policy](https://operations.osmfoundation.org/policies/tiles/). Best-effort service, no bulk/offline prefetch. |
| OpenTopoMap terrain tiles | OpenStreetMap contributors, SRTM, OpenTopoMap; see [provider terms](https://opentopomap.org/about). Retain the provider attribution and CC BY-SA terms. |
| Copernicus DEM GLO-30 | Copernicus DEM public dataset; retain product provenance and the [product license notice](https://copernicus-dem-30m.s3.amazonaws.com/readme.html). A DSM, not surveyed bare-earth road grade. |
| Sentinel imagery | Contains modified Copernicus Sentinel data; source scene/year in manifests. See [Copernicus terms](https://dataspace.copernicus.eu/terms-and-conditions). Optional historical context, not live imagery. |

Generated geographic databases are not relicensed as project code. Large raw and
processed assets are excluded from Git; check source/product terms before
redistributing a map bundle or screenshots. Manifests and provenance files retain
source queries, acquisition metadata and checksums.

## Dependencies

SUMO/TraCI/sumolib are Eclipse SUMO projects under their upstream licenses
(EPL-2.0 / applicable secondary-license terms). H3, FastAPI, Pydantic, HTTPX,
NetworkX, Shapely, pyproj, rasterio, NumPy, Pillow and pytest retain their own
licenses. They are installed as dependencies rather than vendored here. Consult
the installed distributions' license metadata and upstream notices before
redistributing an environment or executable. Tk/Tcl ships with Python separately.
AliveMap's hand-drawn line icons are implemented in `laptop/ui_icons.py`.
