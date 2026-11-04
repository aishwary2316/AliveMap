# Contributing

Start with the [README](README.md), [architecture](docs/architecture.md) and
[testing guide](docs/testing.md). Use Python 3.12 in an isolated environment.
Run from the repository root; install `requirements-dev.txt` for development.

Open an issue describing the expected behaviour, reproduction steps and actual
result. Include OS/Python/SUMO versions and map revision. Remove credentials,
private network addresses and unrelated server records from logs/screenshots.

For a pull request, use a focused branch (for example `fix/route-history`),
explain the user-visible change, and report the exact checks run and any skips.
Preserve independent route computation and the original baseline API contract.
Include meaningful regressions for defects; do not inflate test counts with
implementation-mirroring assertions. Avoid unrelated formatting or generated data.

Map assets, caches, personal reports, credentials and raw deployment inventories
do not belong in Git. Geographic changes need source attribution and provenance.
Never change a shared MEC application, firewall, tunnel or core network as part
of a routine code contribution. Managed deployment requires separate access and
review of the existing application's source, environment and service boundaries.
