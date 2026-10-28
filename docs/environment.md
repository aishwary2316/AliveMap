# Environment discovery

## User-reported context, pending direct inspection

| Component | Reported setup |
| --- | --- |
| Physical MEC | IIIT Manipur, Ubuntu 22.04 |
| Existing API | FastAPI on loopback port 8765 |
| Routes | GET /health, POST /hazards, GET /hazards |
| Geographic indexing | H3 |
| Laptop | Dual boot Ubuntu 24.04 / Windows 11 |
| Access | SSH forwarding, with a supplied jump-host SSH command |

Actual addresses and usernames stay in ignored local SSH configuration.

## Verified in this workspace

- AliveMap was cloned from the designated GitHub repository.
- It initially had no commits or application source.
- Git and Windows OpenSSH clients are available.
- The previous standalone experiment passed local Windows/Python 3.12/SUMO 1.28
  tests. This does not verify physical-MEC integration.
- Password-authenticated SSH discovery through the jump host has succeeded.
- The physical MEC runs Ubuntu 22.04.5 LTS and Python 3.10.12.
- Uvicorn is listening on loopback port 8765.
- GET /health responds successfully and identifies the service as mec-av-poc.
- An existing POC application entrypoint was located. Its contents and API schema
  still need inspection; no remote application has been changed.

## Discovery required before implementation

1. Both SSH hops have worked through an interactive password-authenticated session.
2. Identify the process/service listening on the existing API port.
3. Locate its working directory, application source and Python environment.
   Do not print environment-variable values or unrelated configuration.
4. Inspect relevant source and the actual OpenAPI schema. Establish payload
   fields, coordinate conventions, H3 version/resolution, persistence and
   update/expiration behavior.
5. Identify existing laptop code and SUMO installation, if any.
6. Record a sanitized account of the actual request path and deployment.
7. Review relevant source for secrets before importing it.
8. Design the next increment against that verified baseline.

Initial remote discovery is read-only. The experiment's separate API, companion
port and database are proposals, not facts about the MEC or accepted decisions.