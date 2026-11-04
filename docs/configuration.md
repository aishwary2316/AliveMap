# Configuration and file formats

Run commands from the repository root. The default supported desktop command is
`python -m laptop.map_launcher --playground`; use `--help` for CLI options.
For a fresh checkout, [Setup.ps1](../Setup.ps1) installs and verifies the local
environment in one command; see [setup and replication](setup.md).

## Startup modes

| Launcher | Startup behaviour |
| --- | --- |
| `Open AliveMap Playground.cmd` | Main workspace, editable example, local backend |
| `Open AliveMap MEC.cmd` | Same workspace, configured physical backend |
| `Open AliveMap Maps.cmd` | Geographic workspace without opening the editor example immediately |
| `Open AliveMap Lab.cmd` | Earlier grid/lab diagnostic interface |

The `.cmd` launchers use `.venv/Scripts/pythonw.exe` relative to the checkout.
For startup errors, run the equivalent module with `python.exe` in a terminal
so its traceback remains visible. The main command supports `--playground`,
`--remote`, `--playground-url`, `--mec-url`, `--semantics-url` and `--output`.
The latter two API options also support older compatibility sessions; prefer
the typed playground endpoint for the editable workspace.

## Private client endpoint

The optional `.local/mec-endpoint.json` supports these keys:

| Key | Purpose |
| --- | --- |
| `url` | HTTPS base URL for your managed API |
| `api_key` | Bearer application credential |
| `access_client_id`, `access_client_secret` | Optional paired Cloudflare Access service credentials |

Base-URL selection follows: explicit URL, `ALIVEMAP_MEC_URL`, private-file URL,
then the compatibility loopback default `http://127.0.0.1:18767`. Local mode
injects an in-process HTTP client and does not depend on that remote listener.

Environment variables `ALIVEMAP_API_KEY`, `CF_ACCESS_CLIENT_ID` and
`CF_ACCESS_CLIENT_SECRET` override their file counterparts. File credentials
are used only when the selected hostname matches the configured hostname.
Explicit environment credentials apply to the selected endpoint, so use them
only with its intended URL. User-info, query strings, fragments and non-root
paths are rejected in endpoint URLs. Non-loopback HTTP is rejected.

## Server configuration

| Environment variable | Meaning |
| --- | --- |
| `ALIVEMAP_API_KEY` | Enable shared bearer authentication; configured keys must contain at least 32 characters |
| `ALIVEMAP_STATE_DB` | SQLite file for managed experiment persistence; without it state is in memory |
| `ALIVEMAP_LEGACY_URL` | Reviewed baseline API base URL; defaults to loopback port 8765 |

Run a single API worker. An unauthenticated loopback development instance is
different from an authenticated remote deployment. See
[deployment](permanent-deployment.md) for service guards and ingress boundaries.

## Map providers and cache

The default layers are Streets and Terrain. Optional `.local/map-provider.json`
adds or replaces named tile sources:

```json
{
  "Custom": {
    "url": "https://tiles.example.org/{z}/{x}/{y}.png",
    "attribution": "Provider attribution required by its terms",
    "max_zoom": 19
  }
}
```

This is a schema example, not a working provider. Templates require HTTPS and
all three placeholders. Custom sources have disk caching disabled in the
current implementation. Default sources use `.local/tiles/` and respect the
implemented HTTP cache policy. Do not distribute provider tokens or caches.

## Map packages

`map_packages/<region>/active.json` selects a revision directory. Its manifest
names the graph, attributes, H3 spatial index, SUMO network/config, scenario,
optional rasters and source checksums. The runtime needs the generated files,
not just the committed manifest. Never manually combine a graph or scene from
one revision with another revision's network.

## Saved scenes

Save/Open use JSON with `schema_version`, `map_id`, `map_build_id`, `vehicles`,
`towers` and `anomalies`. Vehicle entries contain legal origin/destination edges,
profile, role and optional along-road insertion position. Towers contain ID,
WGS84 position and radius. Anomalies contain ID, type, Polygon geometry, sensor
reach, lifetime and applicable depth/speed-ratio facts.

Validation currently permits at most 64 vehicles, 32 towers and 32 anomalies.
Vehicle IDs use letters, numbers, underscores or hyphens; `operator` is reserved.
Drawn polygons cannot self-intersect, contain holes or exceed the vertex/area
limits. An area must intersect an eligible road and remain within the map bounds.
Tower radius is 50–10,000 m. Pin placement requires a road within 50 m.

Export stores the initial scene, not a paused SUMO checkpoint. Loading creates
a fresh experiment and checks the exact map build. Runtime delivery history,
acknowledgements and active report versions are not replayed as saved truth.

## Run records

Session outputs are scoped under the selected output root and run UUID.
`events.jsonl` records lifecycle, report and route events. `current.json` is a
periodic inspection snapshot, not a replay checkpoint. SUMO exports such as
`tripinfo.xml` describe the associated run. Run folders, SQLite files, cache,
SSH configuration and credentials are intentionally ignored by Git.
