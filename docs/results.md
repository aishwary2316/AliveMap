# Results and evidence

Results are dated observations, not a claim about current service availability.
All road incidents below are synthetic. Public source data is real geography.

## Setup verification (5 November 2026)

[Machine-readable record](../evidence/setup-verification.json). A separate local
checkout with a new Python 3.12 environment installed the runtime dependencies,
passed `pip check`, built the included real Delhi road source and passed the
two-scout and identical-trip baseline checks. Repeating setup reused the
validated map; its desktop launch was observed healthy in Local mode.

The new verifier also passed on all four existing geographic packages, including
Mayangkhang's legitimate blocked outcome. The portable suite passed 53 tests.
Hosted Windows and Ubuntu jobs both passed for the setup/snapshot source commit.

The test exposed a restricted Windows temporary-directory failure and live
Overpass timeouts/502 responses. The final script uses workspace-local temporary
files and a checksummed, attributed 0.53 MB Delhi OSM snapshot, eliminating live
road-service dependence for default setup. Other regions, refreshed roads and
optional rasters still depend on their sources. Python itself was preinstalled;
this was not a fresh operating-system or physical-MEC deployment test.

## Publication verification (4 November 2026)

The complete Windows regression suite passed **88 tests in one run** (542.89 s).
Final focused packager/endpoint checks passed all 11 tests after configuration
changes. Upstream Starlette/HTTPX and rasterio deprecation warnings remain;
dependencies were not upgraded as part of source cleanup.

A source-only snapshot, excluding private configuration and all prebuilt map
assets, passed 48 portable checks. The documented Delhi roads-only build then
downloaded a fresh OSM extract and converted 14,082 external SUMO edges. It
published revision `a2569bd6f0b4` with explicitly degraded raster status.
Its two-scout story passed with reports at 8.0 and 10.5 simulated seconds and
one computed reroute for the affected receiver. The same test also verified
the identical-trip no-incident baseline. This used the existing pinned local
Python environment, not a newly installed machine or a physical MEC.

The packager/endpoint focused checks passed after hostname generalization.
See [publication verification](../evidence/publication-verification.json) for
the final regression counts and audit scope. Hosted CI results are separate
from these local runs.

## Local Windows campaign (29 October 2026)

[Machine-readable record](../evidence/deployment/workflow-repair-verification.json).
Python 3.12, SUMO 1.28.0, real packaged OSM networks, local API execution.
The full 88-check run initially had one native-form failure. After its repair,
that workflow passed, followed by 14 passing UI regressions. Thus the latest
result for all 88 distinct checks is passing; there was no single final full
88-pass run in that campaign.

| Story | First scout report (sim s) | Second scout report (sim s) | Observed outcome |
| --- | ---: | ---: | --- |
| Delhi urban | 7.5 | 16.5 | Corroborated incident; affected receiver reroutes |
| Gujarat coastal | 13.5 | 23.5 | Corroborated incident; affected receiver reroutes |
| Manipur / Mantripukhri | 10 | 14 | Corroboration and independent receiver rerouting |
| Manipur / Mayangkhang | 44 | 46.5 | Closure leaves no feasible detour; affected followers stop |

`tests/test_story_workflows.py` checks independent discovery times, exactly two
witnesses, H3 cells, assessment, receiving knowledge and valid routes/history.
Its paired no-incident baseline uses identical initial vehicle trips and checks
no incident-induced reroutes. `tests/test_workspace_workflows.py` drives actual
Tk controls and map clicks through drawing, publishing, clearing and vehicle edits.

Reproduce by building all four regions and running:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_story_workflows.py -q -s
.\.venv\Scripts\python.exe -m pytest tests/test_workspace_workflows.py -q
```

Fresh OSM downloads may change the network revision and scenario anchors, so
exact timings are tied to the checked-in historical manifests. Record your own
manifest checksums, dependency versions, command and raw run output when comparing.

## Performance evidence

The historical [map benchmark](../evidence/deployment/map-ui-benchmark.json)
recorded median cached-pan time of 372.66 ms before and 59.35 ms after its tested
optimization. Its fixed viewport/cache setup excludes public tile latency.
The [paced telemetry benchmark](../evidence/deployment/playback-benchmark.json)
recorded 11.59x throughput in a 40-simulated-second headless comparison; it is
not a UI frame-rate, GPU, RF or guaranteed playback-speed measurement.
These measurements predate later repairs; do not present them as fresh release benchmarks.

## Physical MEC and 5G scope

Historical physical-service artifacts under `evidence/` record application-level
integration separately from local tests. They describe specific past runs, not
a public service guarantee. The current two-reporter verifier is
`scripts/verify_mec_story.py`; raw administrative/deployment reports stay private.
No physical server was contacted or changed for this publication cleanup.

**Not verified:** real UE/gNB/UPF transport, RF broadcast, radio latency, actual
sensor detection accuracy, production availability or autonomous-driving safety.
Circular towers and semantic fan-out remain a simulation model even when the
application API runs on physical edge hardware.

## Evidence interpretation

Older artifacts retain their original scope and dates. They are not cumulative
test totals and should not be mixed into one headline success count. Source
provenance records describe geographic inputs; they do not establish incident
truth or prove surveyed road elevations. See [the evidence index](../evidence/README.md).
