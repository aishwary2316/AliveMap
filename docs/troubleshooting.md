# Troubleshooting

Start with Local mode to separate simulation problems from remote connectivity.
Use the Logs, Status and Current state tabs; preserve the first relevant error
and the map revision when reporting a problem.

| Symptom | Check and action |
| --- | --- |
| Launcher closes or no window appears | Run `.venv/Scripts/python.exe -m laptop.map_launcher --playground` from a terminal. Confirm Python/Tk and `requirements-laptop.txt` are installed. |
| Region exists but cannot load | Build it with `python -m geospatial.build <region>`. Git contains manifests, not the large generated assets. Inspect build warnings and staging logs. |
| Build download fails | Public Overpass/raster services may time out. Retry later. Failed builds preserve the previous active revision; do not replace it with a partial folder. |
| Elevation missing after quick start | `--skip-rasters` deliberately makes a roads-only package. Build without that option for DEM acquisition; failed raster sources remain explicitly unavailable. |
| Blank or partial street background | Check the tile-service/network status. Try Terrain or existing cached views. Local roads and live overlays are independent of public imagery. Do not bulk-download tiles as a workaround. |
| Green LOCAL light but no physical reports | Local mode is an in-process backend. Select Physical MEC and load a new scene to use your configured remote service. |
| Remote 401/403 | Check the intended endpoint's credential and optional Access policy privately. Do not put keys in URLs or issue logs. |
| Remote 502/530 or connection refusal | Check your dedicated API and connector health. Try Local for continued local work. Do not change unrelated tunnels, firewall or 5G services. |
| Service reachable but story update required | The client checks schema/delivery/story revisions. Review and update only the managed API; do not weaken the revision check. |
| Vehicle remains queued | Step/resume to allow SUMO insertion. Check directed road, position and nearby vehicles. Manual relocation starts a new driving segment. |
| Circle/rectangle/polygon is visible but vehicles ignore it | A drawing is a draft until saved. Saved ground truth needs a reporter encounter; Publish injects a fact explicitly. Check reporting roles, coverage, sensor reach and Radio events. |
| Polygon Finish fails | Use at least three distinct vertices, no self-intersection, no holes, valid area and an eligible road inside the map. Cancel discards only the draft. |
| Saved vehicle edit seems inactive | Confirm Save succeeded in Logs, then step if the vehicle is queued. Backend/map changes apply on a new load, not to an old session implicitly. |
| No detour after accepted report | Check that the vehicle received the fact, that its future route intersects the area, and that a legal alternative exists. Different policies can retain different routes; blocked is a valid outcome. |
| Old route is only partly dashed | Shared sections remain on the current solid path. Only retired sections are dashed; no history exists before a real route change. |
| Playback pauses after a change | Check Pause on reroute and any connection/validation error. Resume after inspection. The timeline does not support restoring arbitrary past simulation states. |
| Scene rejected after rebuilding maps | Saved scenes bind to a map build. Open the matching revision or recreate the placements on the new graph. Do not silently translate old edge IDs. |
| Remote playback misses a target speed | WAN round trips and server work bound throughput. Compare simulation and wall clocks. Rendering and network waits are different from GPU compute; no GPU speedup is claimed. |
| Pytest cannot create temporary folders | Use a fresh `--basetemp=.local/pytest-diagnostic` path. It must contain no useful files because pytest may replace it. |

## Useful diagnostic commands

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m laptop.map_launcher --help
.\.venv\Scripts\python.exe -m geospatial.build --help
.\.venv\Scripts\python.exe -m pytest -m "not gui and not maps" -q
```

On a managed MEC you administer, inspect only the dedicated AliveMap units
and their logs, as described in [deployment](permanent-deployment.md). Share a
sanitized error summary, reproduction steps and versions; keep raw inventories,
private addresses, credentials and unrelated experiments out of public reports.
