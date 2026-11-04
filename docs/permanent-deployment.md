# Optional physical MEC deployment

Local simulation works without deploying anything. Physical mode is for an
operator-controlled service, not a public demo endpoint supplied by this repo.
Use **Open AliveMap MEC.cmd** only after configuring your own authenticated API.

## Client configuration

Create ignored `.local/mec-endpoint.json` (never commit real values):

```json
{
  "url": "https://edge.example.org",
  "api_key": "REPLACE_WITH_YOUR_PRIVATE_KEY"
}
```

The client verifies TLS and sends bearer authorization. Credentials are not put
in URLs. An explicit URL override does not automatically send file credentials
to another hostname. `ALIVEMAP_MEC_URL` and `ALIVEMAP_API_KEY` support managed
configuration. Optional `CF_ACCESS_CLIENT_ID`/`CF_ACCESS_CLIENT_SECRET` must be
supplied together if your ingress uses Cloudflare Access. Loopback HTTP is
permitted for local development/SSH; remote plain HTTP is rejected.

Select Physical MEC before loading a new scene. An unauthenticated browser may
receive 401: this API is not a map website. Use the workspace connection indicator
and detailed hover error; Reconnect retries the selected backend. A remote
failure is not silently replaced with local simulation evidence.

## Deployment design and boundaries

`mec/playground_api.py` is additive to an existing baseline hazard API. It
performs H3 processing, semantic assessment and scoped application delivery;
it never computes vehicle routes. Single-process SQLite state supports restart
recovery; run one worker. Keep the original baseline private on loopback.

The managed deployment helpers install only the dedicated `alivemap-*` units:

| Unit | Purpose |
| --- | --- |
| `alivemap-playground` | Authenticated loopback API and SQLite state |
| `alivemap-tunnel` | Independent outbound Cloudflare connector |
| `alivemap-baseline-watch` | Guarded availability monitor for a reviewed baseline |

Use a new tunnel, token, hostname and explicit connector configuration. Existing
Cloudflare routes, tokens, applications, Open5GS, MicroK8s and network settings
are outside this installer's scope. Do not use a global connector service
installer over an existing service. DNS/tunnel creation is a separate account
administration step, not performed automatically by the source scripts.

## Operator preparation

These helpers preserve a specific reviewed baseline contract; they are not an
unattended installer for an arbitrary shared server. Before deployment:

1. Establish administrative SSH access and inspect the existing source, Python
   environment, dependencies, working directory, listeners and service lifecycle
   read-only. Review source for secrets and confirm publication/licensing rights.
2. Save access configuration and reviewed inventory only under ignored `.local/`.
   `scripts/mec-inventory.sh` is a read-only discovery aid. Never put passwords
   in a command line, public report or repository.
3. Create `.local/permanent-inspection.json` with the reviewed `home` and `uid`;
   create `.local/alivemap-tunnel.json` with your NEW `tunnel_id` and plain DNS
   `hostname`. Store only its token in `.local/alivemap-tunnel.token`, with
   user-only permissions. The packager checks token/tunnel identity and rejects
   a pending endpoint configuration for a different hostname.
4. Review `deployment/install_permanent.py`, the three service templates and
   guard assumptions against the inspected server. The installer verifies source
   identity, service ownership, port availability and dependency readiness.
5. On Windows run `scripts/Install-PermanentMec.ps1` with your private SSH config
   and host alias. It collects sudo/SSH authentication interactively and creates
   a secret-bearing ignored payload. Never attach that payload to an issue.
6. Configure only the new ingress to the dedicated loopback API. Check unauthenticated
   rejection, authenticated health, persistence and one scoped scenario before use.

The installer refuses implicit credential rotation. Its private inspection,
source-hash and service assumptions must match your server; do not weaken guards
just to pass an install. Original baseline data is memory-only; new experiment
state has a separate SQLite store. `/legacy/*` is narrowly limited compatibility
forwarding, not an unrestricted reverse proxy.

## Updates, recovery and verification

`Update-PlaygroundMec.ps1` packages an API-only update using the previous private
payload and expected source identity. It replaces only the managed API source,
backs it up, verifies readiness/preserved experiments and rolls back on failure.
It does not edit DNS, tunnels or core-network configuration.

```sh
systemctl status alivemap-playground alivemap-tunnel alivemap-baseline-watch
journalctl -u alivemap-playground -u alivemap-tunnel
```

`scripts.verify_mec_story` explicitly tests one real SUMO story through your
configured HTTPS service. It cleans only its own experiment and checks unrelated
records remain intact. See [testing](testing.md). Administrative recovery scripts
can deliberately crash/restart the dedicated API: schedule them separately from
normal simulations and review their active-experiment guards first.

Historical integration evidence is described in [results](results.md). It does
not establish current uptime or real UE/gNB/UPF transport. Cloudflare provides
application reachability; measure the private 5G path separately before making
radio or end-to-end cellular latency claims.
