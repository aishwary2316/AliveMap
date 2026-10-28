"""Public, attributable OSM / Copernicus / Sentinel acquisition; bounded rasters."""
import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import box, shape

USER_AGENT = "AliveMapResearch/0.3 (Windows SUMO map-package research)"


def utc():
    return datetime.now(timezone.utc).isoformat()


def request(url, data=None, timeout=100):
    headers = {"User-Agent": USER_AGENT}
    if data is not None:
        data = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=timeout) as response:
        return response.read()


def osm_query(bounds):
    west, south, east, north = bounds
    bbox = f"{south},{west},{north},{east}"
    return f'[out:xml][timeout:90];(way["highway"]["area"!="yes"]({bbox});relation["type"="restriction"]({bbox}););(._;>;);out meta;'


def roads(bounds, destination):
    query = osm_query(bounds)
    errors = []
    for endpoint in ("https://overpass.private.coffee/api/interpreter", "https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"):
        try:
            content = request(endpoint, {"data": query})
            if b"<osm" not in content or b"<way " not in content or b"<remark>" in content:
                raise ValueError("OSM source returned no ways or an error remark")
            destination.write_bytes(content)
            return {"product": "OpenStreetMap road extract", "source_url": endpoint, "query": query,
                    "acquired_at": utc(), "license": "ODbL-1.0", "attribution": "© OpenStreetMap contributors",
                    "license_url": "https://www.openstreetmap.org/copyright"}
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("Road download failed: " + "; ".join(errors))


def clip_cog(url, bounds, destination, max_dimension=2400):
    """Retain a georeferenced source-window subset, not the entire large COG."""
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                      GDAL_HTTP_TIMEOUT="35", GDAL_HTTP_MAX_RETRY="2", GDAL_HTTP_RETRY_DELAY="1"):
        with rasterio.open(url) as src:
            extent = transform_bounds("EPSG:4326", src.crs, *bounds, densify_pts=21)
            # Intersect requested footprint with this source's coverage before reading.
            left, bottom = max(extent[0], src.bounds.left), max(extent[1], src.bounds.bottom)
            right, top = min(extent[2], src.bounds.right), min(extent[3], src.bounds.top)
            if left >= right or bottom >= top:
                raise ValueError("Raster does not overlap footprint")
            window = from_bounds(left, bottom, right, top, src.transform).round_offsets().round_lengths()
            factor = max(1, max(window.width, window.height)/max_dimension)
            width, height = max(1, round(window.width/factor)), max(1, round(window.height/factor))
            values = src.read(window=window, out_shape=(src.count, height, width))
            transform = src.window_transform(window) * src.transform.scale(window.width/width, window.height/height)
            profile = dict(driver="GTiff", width=width, height=height, count=src.count,
                           dtype=values.dtype, crs=src.crs, transform=transform, compress="deflate",
                           nodata=src.nodata)
            with rasterio.open(destination, "w", **profile) as dst:
                dst.write(values)
            return {"source_url": url, "source_crs": str(src.crs), "source_resolution": list(src.res),
                    "subset_crs": str(src.crs), "subset_resolution": [abs(transform.a), abs(transform.e)],
                    "subset_operation": "georeferenced footprint window; bounded read", "nodata": src.nodata}


def mosaic(paths, destination, nodata):
    datasets = [rasterio.open(path) for path in paths]
    try:
        values, transform = merge(datasets, nodata=nodata)
        profile = datasets[0].profile.copy()
        profile.update(height=values.shape[1], width=values.shape[2], transform=transform,
                       nodata=nodata, compress="deflate", driver="GTiff")
        with rasterio.open(destination, "w", **profile) as dst:
            dst.write(values)
    finally:
        for dataset in datasets:
            dataset.close()


def elevation(bounds, source_dir):
    west, south, east, north = bounds
    tiles, metadata = [], []
    tile_dir = source_dir / "elevation_tiles"
    tile_dir.mkdir(exist_ok=True)
    for lat in range(math.floor(south), math.floor(north)+1):
        for lon in range(math.floor(west), math.floor(east)+1):
            name = f"Copernicus_DSM_COG_10_{'N' if lat >= 0 else 'S'}{abs(lat):02d}_00_{'E' if lon >= 0 else 'W'}{abs(lon):03d}_00_DEM"
            url = f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"
            path = tile_dir / f"tile{len(tiles)}.tif"
            metadata.append(clip_cog(url, bounds, path))
            tiles.append(path)
    mosaic(tiles, source_dir / "elevation.tif", -9999)
    return {"product": "Copernicus DEM GLO-30 Public, 2021 release", "surface_model": "DSM; includes surface objects",
            "vertical_units": "metres", "vertical_datum": "EGM2008 orthometric heights",
            "nominal_sampling_m": 30, "acquired_at": utc(), "tiles": metadata,
            "source_url": "https://registry.opendata.aws/copernicus-dem/",
            "license": "Copernicus DEM GLO-30 public licence",
            "license_url": "https://copernicus-dem-30m.s3.amazonaws.com/readme.html",
            "attribution": "Copernicus DEM, © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018"}


def satellite(bounds, source_dir):
    endpoint = "https://earth-search.aws.element84.com/v1/search"
    parameters = {"collections": "sentinel-2-l2a", "bbox": ",".join(map(str, bounds)),
                  "datetime": "2024-01-01T00:00:00Z/2024-12-31T23:59:59Z", "limit": 40,
                  "query": json.dumps({"eo:cloud_cover": {"lt": 20}})}
    url = endpoint + "?" + urllib.parse.urlencode(parameters)
    catalogue = json.loads(request(url, timeout=45))
    (source_dir / "satellite-catalogue.json").write_text(json.dumps(catalogue, indent=2), encoding="utf-8")
    candidates = [item for item in catalogue.get("features", [])
                  if item.get("assets", {}).get("visual", {}).get("href", "").endswith(".tif")]
    candidates.sort(key=lambda item: (not shape(item["geometry"]).covers(box(*bounds)), item["properties"].get("eo:cloud_cover", 100), item["id"]))
    if not candidates:
        raise ValueError("No cloud-filtered Sentinel-2 L2A visual COG found")
    selected, coverage = [], None
    for item in candidates:
        polygon = shape(item["geometry"])
        if coverage is not None and coverage.covers(polygon.intersection(box(*bounds))):
            continue
        selected.append(item)
        coverage = polygon if coverage is None else coverage.union(polygon)
        if coverage.covers(box(*bounds)):
            break
        if len(selected) == 4:
            break
    if not coverage.covers(box(*bounds)):
        raise ValueError("Available scenes do not fully cover the map footprint")
    tiles, records = [], []
    tile_dir = source_dir / "satellite_tiles"
    tile_dir.mkdir(exist_ok=True)
    for item in selected:
        path = tile_dir / f"scene{len(tiles)}.tif"
        metadata = clip_cog(item["assets"]["visual"]["href"], bounds, path)
        records.append({**metadata, "item_id": item["id"], "datetime": item["properties"]["datetime"],
                        "cloud_cover_percent": item["properties"].get("eo:cloud_cover"),
                        "stac_geometry": item["geometry"]})
        tiles.append(path)
    mosaic(tiles, source_dir / "satellite.tif", 0)
    return {"product": "Copernicus Sentinel-2 L2A natural colour (TCI)", "nominal_sampling_m": 10,
            "acquired_at": utc(), "scenes": records, "source_url": url,
            "license": "Copernicus Sentinel free, full and open access terms",
            "license_url": "https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice",
            "attribution": "Contains modified Copernicus Sentinel data 2024, accessed via Element 84 Earth Search",
            "warning": "Historical context imagery; cloud cover is catalogue-wide, not a local cloud assessment"}
