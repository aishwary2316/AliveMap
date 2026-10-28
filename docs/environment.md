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
- The attempted jump-host connection failed before remote authentication.

## Discovery required before implementation

1. Verify both SSH hops, host keys and authentication.
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