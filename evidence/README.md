# Verification evidence

These records describe actual runs. Local tests and physical-MEC runs are separate.

The controller event logs contain only this POC's synthetic reports and routing
decisions. Raw SSH inventories, access details and pre-existing MEC hazard contents
are private and excluded. SUMO XML exports have local-path comments removed; raw
original output remains in the ignored runs/ directory.

The direct physical-MEC run used the existing API reached through authenticated
SSH forwarding, following direct inspection of its source, schema, environment,
process command and working directory. This is application-level integration
evidence; it does not prove a 5G user-plane path or measure radio latency.

The semantic extension is now deployed and healthy on the physical MEC. The
`physical-mec-view-manual/` evidence records the GUI step and warning/closure/clear
flow through that deployed view. It is separate from the complete arrival run
against the original API; no complete physical arrival run through the view is
claimed by the manual evidence.
