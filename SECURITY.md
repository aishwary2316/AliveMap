# Security

Do not put API keys, tunnel tokens, SSH/sudo passwords, private addresses or raw
server inventories in issues or pull requests. Configure credentials only in
ignored `.local/` files or the documented environment variables.

Remote endpoints require HTTPS; certificate validation and credential-host
binding must remain enabled. The baseline API is a compatibility reference,
not a service to expose directly to the Internet. Keep managed APIs on loopback
behind an authenticated ingress. Current bearer authentication is a shared
application credential, not per-device identity or production authorization.

For a suspected vulnerability, use GitHub's **Report a vulnerability** privately
if the maintainer has enabled it. If unavailable, open a minimal issue requesting
a private contact without posting exploit details or secrets. No security email
or response-time guarantee has been designated yet.

If a secret reaches Git, revoke/rotate it first. Removing it from a new commit
does not remove history or copies. Coordinate any history rewrite with maintainers;
never force-push a shared branch as routine cleanup.
