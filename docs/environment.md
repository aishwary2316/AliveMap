# Environment discovery

## Directly verified on 28 October 2026

| Component | Observation |
| --- | --- |
| Physical MEC OS | Ubuntu 22.04.5 LTS |
| Server Python | 3.10.12 |
| Existing application | FastAPI/H3 POC; source reviewed and imported into mec/baseline/ |
| Listener | Uvicorn on 127.0.0.1:8765 |
| Launch | POC .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8765, using its .venv Python |
| Working directory | Existing POC project directory |
| Process lifecycle | Current process belongs to a login-session scope; automatic restart/startup has not been verified |
| Health | Successful response, service mec-av-poc |
| Live API | GET /health, POST /hazards, GET /hazards |
| H3 resolution | 10, computed by the actual source |
| Storage | Process-memory dictionary keyed by event_id |
| Runtime packages | Observed in the POC .venv; recorded in mec/baseline/requirements-observed.txt |
| Access | Both SSH hops worked using interactive password authentication |
| Repository | AliveMap, initially empty; now the project source of record |
| Local desktop | Windows; project test environment uses Python 3.12 |

The actual API contract is documented in mec-api-contract.md. The source was
reviewed for credentials before importing it. The source, schema and application
package metadata were read without modifying the server.

## Still reported, rather than directly verified

- The laptop also boots Ubuntu 24.04.
- The intended deployment uses a 5G MEC communication path.
- Existing laptop SSH forwarding worked in the earlier setup. A subsequent local
  request to port 8765 did not respond within three seconds; no usable tunnel is
  currently assumed by this workspace.

## Remaining discovery before deployment

1. Launch command and working directory are verified. Establish restart/startup
   behavior before deployment; the current process belongs to a login session.
2. Identify any existing SUMO/controller work on the laptop's Ubuntu installation.
   No SUMO binary is currently on the Windows command search path. The previous
   experiment installed SUMO separately in an isolated environment.
3. The user authenticated a persistent SSH connection. Forwarding and health are
   now directly verified, as is an actual SUMO/controller run against the physical
   API: all 13 checks passed. Keep its tunnel open during further testing.
4. Verify the intended network path separately before claiming 5G measurements.
5. The additive read-only semantic view is implemented and locally tested. Its
   guarded physical deployment and verification remain pending. It reads the
   existing store without restarting the API or altering its environment.

## Local working setup

The repository's .venv is separate from the earlier experiment's environment.
requirements-dev.txt uses the observed MEC package versions plus local test tools. Installation completed after package-download timeouts. All 19 local tests pass, including exact comparison with the observed live OpenAPI schema and checks for the actual client, mapping, routing and semantic view.
Local tests run on Windows/Python 3.12; this does not substitute for validation on
Ubuntu/Python 3.10 at the physical MEC.

Actual addresses, usernames, connection scripts and raw discovery output stay in
ignored .local/. Passwords are entered into SSH and are not stored in Git.
The previous standalone experiment remains under experiments/standalone-poc/;
its separate API and database are not the existing MEC architecture.