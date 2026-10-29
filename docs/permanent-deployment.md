# Permanent AliveMap connection

The deployed API is **https://alivemap.aishtrex.com**. Double-click
**Open AliveMap MEC.cmd**, choose **Load example** or **Empty playground**, then
Resume. The main window displays the actual endpoint. The private laptop
configuration selects the HTTPS address and supplies its application credential.
No SSH window, laptop port forward or Ubuntu jump VM is required for simulation.
SSH remains an administrative setup/recovery tool.

Opening the URL in an ordinary browser returns **401 Authentication required**.
That is expected: this is an authenticated API, not a public map website.
The laptop controller supplies its bearer credential automatically. TLS
certificates are verified; credentials are never placed in URLs or run logs.

## Isolated deployment

AliveMap uses a new tunnel named `alivemap-mec`, a new DNS hostname, a dedicated
connector token and `/etc/alivemap/tunnel.yml`. The explicit connector config
prevents automatic discovery of a pre-existing `~/.cloudflared/config.yml`.
The existing Cloudflare tunnel, routes, credentials, service and applications
were not modified or restarted. The installed cloudflared executable is reused
without updating or replacing it.

| New service | Purpose |
| --- | --- |
| `alivemap-playground.service` | Authenticated API on loopback8768, one worker, SQLite state |
| `alivemap-tunnel.service` | Dedicated outbound Cloudflare connector, independent of SSH |
| `alivemap-baseline-watch.service` | Monitor the reviewed original API; start its unchanged source only if absent |

All three units are enabled for boot and have restart policies. An actual
controlled crash verified API automatic recovery. The MEC was **not rebooted**
as a test, to preserve its other running applications.

The original project hazard API remains on8765. Existing live processes are
preserved. Its availability supervisor checks its source hash and refuses to
duplicate an existing process or replace an occupied listener. It does not change
the original source or Python environment. The older8766 view and8767 playground
are independent of this managed deployment and are not published by this tunnel.

The baseline's original event dictionary remains memory-only. The new typed API
persists its own experiment state, incident versions, acknowledgements, H3 areas
and delivery history in `/var/lib/alivemap/playground.sqlite3`. Wall-clock expiry
continues across restarts; restarting does not renew incidents. Persistence is
single-process SQLite with WAL and full synchronous commits. The existing
guided/grid protocol is available through authenticated, narrowly limited
`/legacy/health`, `/legacy/openapi.json` and `/legacy/hazards` forwarding.

## Credentials

The laptop's ignored `.local/mec-endpoint.json` contains the endpoint and API key.
Its Windows file permissions are restricted to the current user. An environment
override `ALIVEMAP_MEC_URL` or an explicit CLI URL can select another endpoint;
file credentials are not automatically forwarded to another hostname. Loopback
HTTP remains supported for local testing and older SSH operation. Remote
endpoints require HTTPS and redirects are not followed with credentials.

On MEC, `/etc/alivemap/api.env` and `/etc/alivemap/tunnel.token` have restricted
permissions. The tunnel credential belongs only to the new AliveMap tunnel.
Neither API keys, tunnel tokens nor SSH/sudo passwords belong in Git. The
installer collects passwords through hidden terminal input and sends them only
through authenticated SSH. It does not save the sudo/SSH passwords.

Application bearer authentication protects the API. Cloudflare Access service
headers are supported by the client for an optional additional Access policy;
such a policy is not claimed as part of this deployment. Per-device credentials
and MQTT messaging remain separate future work.

## Reproducible setup and administration

`deployment/*.service.in` contains the service templates. The root-side scoped
installer is `deployment/install_permanent.py`; it checks the baseline hash,
account identity, free/new service port, dedicated service ownership and existing
credentials. It refuses implicit credential rotation and never edits the
pre-existing Cloudflare configuration or service. Sources are content-addressed
under the service account's `alivemap-services/` directory.

`scripts/package_permanent.py` builds an ignored checksummed deployment payload.
It accepts Windows PowerShell UTF-16/BOM inspection files as well as UTF-8.
`scripts/Install-PermanentMec.ps1` privately collects the new tunnel credential,
checks its tunnel ID, asks for sudo and SSH passwords, and installs only the
three named units. It never invokes cloudflared's global service installer.

For logs and status on MEC:

    systemctl status alivemap-playground alivemap-tunnel alivemap-baseline-watch
    journalctl -u alivemap-playground -u alivemap-tunnel -u alivemap-baseline-watch

If a future deployment changes the original API source, review its new source
and update the supervisor's expected hash deliberately. It fails safely rather
than automatically running unreviewed replacement source.

## Verification

The public HTTPS endpoint was checked for valid certificates, authenticated200,
unauthenticated401, persistent state and guided-controller compatibility.
The real Delhi SUMO run completed all15 physical checks over HTTPS: perception,
MEC H3, per-vehicle delivery, offline exclusion, a driven detour, all four arrivals,
multiple incidents, selected clearance, buffered upload and scoped cleanup.

    .\.venv\Scripts\python.exe -u -m scripts.verify_physical_playground --url https://alivemap.aishtrex.com --evidence evidence/deployment/https-sumo-verification.json

`scripts/Verify-PermanentMec.ps1` performs an administrative recovery test only
when there are no active managed experiments. It saves its own test incident,
crashes only the dedicated AliveMap API process, checks automatic restart and
incident/deduplication recovery, then clears its test data. It checks original
Cloudflare process/configuration and original API records/source for changes.
It does not restart the existing applications or reboot MEC.

The client retries transient transport/5xx errors for reads, full tower updates,
equal-time telemetry and versioned incident reports. Retries are bounded and
do not bypass authentication, validation, coverage or stale-version failures.
Registration and deletion retain single-request behavior. A sustained outage
can still pause simulation and require Reconnect; no empty or cleared state is
invented after an error.

The simulation still uses synthetic tower coverage and HTTP application fan-out.
This deployment does not establish an actual UE/gNB/UPF path or RF broadcast.
The Cloudflare route is appropriate for remote access; private 5G latency tests
must measure the actual cellular path separately.
