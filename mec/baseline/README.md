# Observed MEC baseline

This is the existing POC source inspected over password-authenticated SSH on
28 October 2026. It is a reference snapshot, not a new implementation or a
deployment instruction. The server was not modified.

main.py was reviewed before publication: it contains API code, no credentials,
private host addresses or database connection strings. The retrieved source
normalizes to 990 UTF-8 bytes, matching the remote file's observed size.
Its local SHA-256 is:

    45a06e0e9496df0cb2f9a80f330f6da998c787aba3df4c67d8d37407a13708c5

openapi-observed.json is the schema fetched from the running physical service.
requirements-observed.txt records application dependency versions installed in
the POC's own .venv, excluding pip and setuptools. This is an observed snapshot,
not a proposed dependency upgrade. The server uses Python 3.10.12.

The reference app deliberately retains the existing in-memory event dictionary
and API behavior. Do not overwrite the remote application with experiment code.