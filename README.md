# AliveMap

5G MEC autonomous-routing proof of concept using SUMO, TraCI and an existing
FastAPI/H3 service on a physical MEC server.

## Current status

The repository was empty when cloned on 28 October 2026. Workspace setup is in
progress. The existing MEC source has not yet been retrieved or inspected.
SSH access was blocked locally before remote authentication. Environment
discovery must complete before the experiment is adapted or deployed.

The existing working API and SSH forwarding are reported by the user; they have
not yet been independently verified from this workspace.

## Layout

- docs/environment.md: known context and remaining discovery.
- scripts/mec-inventory.sh: read-only initial server discovery.
- experiments/standalone-poc/: previous code, retained for review.
- .local/ (ignored): actual SSH configuration and private discovery output.

The experiment includes a SUMO controller, network generation, independent
per-vehicle graph routing, directed-lane mapping, a standalone semantic API and
local tests. It must not be deployed as a replacement for the existing application.

This repository is public. Credentials, private access details and raw server
output are excluded.