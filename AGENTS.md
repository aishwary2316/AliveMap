# AliveMap project instructions

AliveMap is the source repository for the user's 5G MEC autonomous-routing POC.

Before adapting or deploying code:
1. Establish SSH access through the user's jump host. Connection details belong
   in ignored .local/, not this public repository.
2. Inspect the existing MEC application's source, process/service, Python
   environment, dependency versions and API contract before proposing integration.
3. Keep initial remote discovery read-only. Do not install, restart, reconfigure
   or deploy applications during discovery.
4. Preserve existing applications, Open5GS and MicroK8s.
5. Review remote source for secrets before importing it. Never commit credentials,
   environment files, raw inventories or private network topology.
6. Separate user-reported context from directly verified observations.

experiments/standalone-poc preserves an earlier locally tested experiment created
before environment discovery. It is not an accepted deployment design and its
separate API is not the existing MEC application.

Use explicit repository working directories. Report local simulation, physical-MEC
integration and 5G-path verification separately. No fabricated deployment evidence
or hardcoded alternative routes.