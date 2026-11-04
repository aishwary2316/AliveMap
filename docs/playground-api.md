# Typed MEC API

Implementation: `mec/playground_api.py`. This is the active editable-workspace
contract; [the baseline contract](mec-api-contract.md) describes compatibility.
The configured server exposes its generated schema at `/openapi.json`. When
authentication is enabled, that request also needs the bearer credential.

| Method and path | Request / purpose |
| --- | --- |
| `GET /health` | Service identity, schema/delivery/story revisions and experiment count |
| `POST /v1/experiments` | UUID `experiment_id`, `map_id`, WGS84 `bounds`, `towers` |
| `PUT /v1/experiments/{id}/towers` | Full tower list replacement |
| `POST /v1/experiments/{id}/tick` | Nondecreasing `sim_time`, vehicle positions and roles; returns network snapshot/deliveries |
| `POST /v1/experiments/{id}/observations` | Versioned synthetic sensor report or explicit operator injection |
| `GET /v1/experiments/{id}` | Current scoped snapshot |
| `DELETE /v1/experiments/{id}` | Clear this experiment's bridged reports and remove its state |

The schema defines bounds and count limits. Unknown model fields and nonfinite
numbers are rejected. Towers carry `id`, longitude, latitude and radius. Vehicles
carry `id`, longitude, latitude and `role` (`reporter`, `receiver`, `both`, `offline`).

An observation contains `incident_id`, `vehicle_id`, position, `kind`, Polygon
`geometry`, typed semantic `facts`, positive `event_version`, wall-clock `ttl_s`
and `source_type`. Facts use `traffic_speed_ratio` for congestion and
`water_depth_m` for flood; landslide represents closure. Clearance is a new
version with kind `clear`. Area geometry must fit the selected experiment.

The service checks reporting role/coverage and rejects stale versions or a
conflicting equal-version fingerprint. Equal-version independent reports can
corroborate the same incident; identical retransmissions do not create witnesses.
Expiry continues across persistent-state recovery. Failed cleanup retains the
experiment so the operator can retry rather than falsely reporting success.

Assessment is deliberately transparent: closure severity 1; flood depth/0.5 m
capped at 1; congestion 1 minus speed ratio. Priority is critical at severity
0.8 or above, high at 0.4 or above, otherwise moderate. Independent witnesses
exclude the operator; two yield `corroborated`. These rules are POC policies.

Snapshots expose incident H3 cells at resolutions 8/10, assessments, simulated
tower associations and vehicle-specific delivery state. Routes are absent:
each vehicle plans on the laptop from its own delivered facts.

The API uses an optional shared bearer key for deployment, verified HTTPS at
ingress, bounded client retries and single-process SQLite persistence. It is
not a production multi-tenant authorization service. Current delivery is HTTP
request/response; MQTT, PC5 and real cellular broadcast are not implemented.
