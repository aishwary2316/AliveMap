# Evidence index

These checked-in artifacts describe historical runs, not current availability.
The maintained interpretation is [results and limitations](../docs/results.md).

| Directory | Scope |
| --- | --- |
| `deployment/` | Dated workspace, transport, rendering and recovery checks; each JSON has its own scope |
| `maps/` | Geographic input provenance, build checks and earlier scenario comparisons |
| `local-direct/`, `local-with-view/` | Earlier deterministic grid runs using a local baseline API |
| `physical-mec-direct/`, `physical-mec-view-manual/` | Earlier application integration and manual semantic-view checks |
| `playground/` | Earlier local and physical playground acceptance runs |

The publication cleanup's full 88-pass run, source-only tests and fresh Delhi
build are recorded in [publication-verification.json](publication-verification.json).
The earlier repair campaign is
[workflow-repair-verification.json](deployment/workflow-repair-verification.json).
It reports a full run with one defect, followed by successful repair/reruns, not
one uninterrupted all-pass run. Historical totals are not cumulative.

Synthetic reports and per-vehicle route decisions are not real-world incident
detections. Physical API evidence does not establish a UE/gNB/UPF or RF path.
Private credentials, raw inventories and new detailed administrative reports
remain outside Git. Keep new raw runs under ignored `runs/`; publish only a
reviewed, scoped result with methodology and limitations.
