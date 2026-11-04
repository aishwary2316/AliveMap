# Setup and replication

## Windows: first installation

1. Install [Git for Windows](https://git-scm.com/downloads/win) and Python
   **3.12** from the [official Windows downloads](https://www.python.org/downloads/windows/).
   Choose a 3.12 installer rather than the newest major Python version. In the
   Python installer include the Python launcher and Tcl/Tk. Other installed
   Python versions can coexist; this project uses its own `.venv`.
2. Open PowerShell in a writable working folder and clone:

   ```powershell
   git clone https://github.com/aishwary2316/AliveMap.git
   cd AliveMap
   powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1
   ```

3. Wait for all four setup stages. The first run downloads Python packages and
   converts the bundled real Delhi OpenStreetMap extract into a validated SUMO map.
   A real headless simulation checks independent reporting and rerouting before
   the desktop opens. Package download times depend on connectivity.
   Expect several hundred megabytes of package downloads; the pinned Windows
   SUMO/data wheels alone are approximately 274 MB. Normal launches reuse them.
   Delhi's source snapshot is included in Git and needs no Overpass request.
   Other regions and explicit refreshes use public fallback services; an
   individual source can take up to 100 seconds before timeout and fallback.
4. In the workspace use **Local**, **Delhi Urban**, **With incident**, then Run.
   Follow Blue to inspect its current route. After both scouts report, inspect
   the corroboration log and dashed retired route. Choose **Without incident**
   and Run to compare identical initial trips.

The script needs no administrator, SSH, Cloudflare login or API key. Its
`ExecutionPolicy Bypass` option is process-scoped; it does not change the
machine's saved execution policy. Setup deliberately does not install Python
or change system networking. If Python is missing, it stops with instructions.

## Setup options

```powershell
# Install, build Delhi and verify without opening the desktop
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -NoLaunch

# Build Delhi, Gujarat and both Manipur subregions
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -AllMaps

# Attempt DEM and historical imagery downloads too
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -AllMaps -Terrain

# Fetch new live OSM road extracts instead of reusing maps/snapshots
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -RefreshMaps -NoLaunch

# Include pytest for development
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -Dev -NoLaunch

# Use an explicitly installed portable/unregistered Python 3.12
powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup.ps1 -PythonExe C:\Python312\python.exe
```

`-SkipCheck` skips the real simulation acceptance step; use it only when you
intentionally want installation without verification. It does not make a failed
map build succeed. `-Terrain` uses the full map builder, which also attempts
historical imagery; missing optional rasters are recorded as degraded status.
It does not promise satellite imagery suitable for detailed inspection.

The underlying cross-platform command is:

```powershell
py -3.12 scripts/setup_local.py --maps delhi_urban --launch
```

Options are `--maps <one or more region IDs or all>`, `--terrain`, `--dev`,
`--refresh-maps`, `--skip-check` and `--launch`. Omitting `--launch` performs a headless install/check.

## What setup writes

| Location | Contents |
| --- | --- |
| `.venv/` | Isolated Python runtime packages |
| `map_packages/<region>/` | Source, processed graph, SUMO network and selected manifest revision |
| `.local/setup-temp/` | Private temporary files for package/bootstrap work |
| `runs/setup-verification/` | Actual local scenario logs and `verification.json` |

It checks Python version, bootstraps pip, installs the pinned requirement set,
runs `pip check`, checks Tk import and the SUMO executable, validates/builds maps,
and runs `scripts.verify_local`. That verifier uses in-process APIs with a local
baseline bridge. It ignores remote API/state environment settings for this check;
it neither contacts physical MEC nor reads its credentials.

## Repeating setup and normal launches

Run the same command after an interrupted download or on an existing checkout.
Pip reuses satisfied dependencies. Complete map packages are checksum-validated
and reused. An existing Python environment of the wrong version is rejected,
not deleted. A partial environment with Python present can bootstrap pip again.
Missing/corrupt maps are rebuilt; failed builds leave the previous active pointer
unchanged and retain staging logs. No update is sent to a remote service.
If a rebuilt revision has the same identity as an existing folder, its old files
are retained under `map_packages/.staging/retained-*` before replacement. A failed
publication restores that folder. Setup does not delete the retained copy.

After setup, double-click **Open AliveMap Playground.cmd** for daily use. To
repeat only the simulation check:

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_local --maps delhi_urban
```

For one additional region, without rebuilding other packages:

```powershell
py -3.12 scripts/setup_local.py --maps gujarat_coastal
```

## Linux

Use an installed Python 3.12 with `venv`/`ensurepip` and Tk support, plus Git.
On Ubuntu these are commonly provided by `python3.12-venv` and `python3-tk`
when Python 3.12 is available through your distribution. Install prerequisites
through your normal package manager; this script does not elevate privileges.

```sh
git clone https://github.com/aishwary2316/AliveMap.git
cd AliveMap
python3.12 scripts/setup_local.py
.venv/bin/python -m laptop.map_launcher --playground
```

Omit the last command on a headless host. Native Linux desktop appearance has
not received the same UI verification as Windows. Portable CI and headless
simulation are separate from native desktop validation.

## Replicate a recorded result

For an exact source revision, check out its commit before running setup. Record
the source commit, requirement versions, region and map build ID with the result.
The verification JSON records report times and the build actually used.

The default Delhi setup uses the same attributable source snapshot shipped with
the selected source commit. Its compressed and XML checksums are verified before
conversion. This pins geographic input while routes are computed at runtime.
SUMO/platform versions and recipe changes can affect build identity. Explicit
refreshes and other regions can change road data, scenario anchors and timings.
Exact historical packages still require matching their manifest checksums;
changed source data is not a bit-identical reproduction.

Physical MEC replication is a separate operator-controlled deployment described
in [the deployment guide](permanent-deployment.md); laptop setup does not create
credentials, tunnel accounts or modify shared infrastructure. See
[troubleshooting](troubleshooting.md) and [testing](testing.md) for failures and checks.
