# Release preparation

The source cleanup does not create a GitHub release, rewrite history, publish a
package or grant a code license. Before the first open-source release:

1. Choose the project code license and confirm the right to license the imported
   baseline snapshot and contributions. Add the appropriate license text and
   notices; update the README and contributing guide. Licensing is maintained by the project owner.
2. Review the exact release diff and repository history for secrets, personal
   files and infrastructure metadata. Pattern scanning is not a guarantee.
   If a real secret is discovered, rotate it and coordinate any history rewrite.
3. Build at least Delhi from a fresh clone, run the local story and both incident
   modes. Review source licenses before distributing generated map bundles.
   Map manifests alone are not runnable assets.
4. Run the documented portable/full suites and inspect hosted CI results. Record
   pass/fail/skip counts, environment, source revision, map revisions and dates.
   Keep physical-service evidence separate and sanitized; never imply RF proof.
5. Choose a version, update the changelog, tag the reviewed commit and publish
   release notes with requirements, known limits and reproducible commands.

The initial release is a source checkout workflow, not a Windows installer or
PyPI package. Runtime dependencies are pinned; transitive dependency snapshots
and binary redistribution licenses still need review if packaging an executable.
Do not bundle private `.local/`, raw runs, caches or a working virtual environment.
