# Changelog

## Unreleased

### Documentation reference

- Added software/provider inventory, routing equations and profiles, configuration
  reference, saved-scene semantics and troubleshooting instructions.
- Replaced workstation-specific completion prompts with operator instructions.
- Corrected the hosted dependency-cache inputs to match the requirement filenames.

### Publication preparation

- Replaced session-specific setup instructions with a local-first quick start,
  architecture, test tiers, evidence interpretation and deployment guidance.
- Retired the unused pre-discovery standalone prototype; retained its Git-history
  reference and the active baseline compatibility implementation.
- Removed the development-only Delhi probe-reuse switch from the map builder;
  published source builds acquire and record their own real road extract.
- Separated runtime/API dependencies from development tools, pinned the direct
  NumPy dependency and added Windows/Ubuntu portable-test workflow configuration.
- Made the deployment packager's hostname come from private operator configuration
  instead of a particular installation; retained token and hostname guards.
- Excluded personal reports, screenshots, shortcuts and publication drafts from Git.
- Documented third-party data attribution and security guidance.

### Existing simulation

- Single-window editable real-map SUMO workspace with independent vehicle routes.
- Local/remote typed MEC API, H3 areas, simulated tower-scoped delivery, independent
  scout corroboration, route-history display and with/without incident stories.
- Bounded background map/network work and responsive dark workspace controls.

Historical measurements are in [results](docs/results.md). No release version or
production/real-5G validation is implied by this changelog.
