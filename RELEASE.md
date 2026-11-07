# Publishing the SDKs

The public distribution name is `buildsol` on both registries. Version 0.1.0 remains the initial GitHub-only release; 0.1.1 adds registry distribution and updated installation instructions without API behavior changes.

1. Run the Python and JavaScript tests, build the distributions and inspect package contents.
2. Record every archive's byte size and SHA256 in `releases/<version>.json`.
3. Create the matching GitHub release with those exact archives and `SHA256SUMS`.
4. Check that the version does not already exist in either registry.
5. npm: sign in with `npm login --auth-type=web`, then publish the reviewed `.tgz` with `npm publish <archive> --access public`.
6. PyPI: configure a Trusted Publisher for owner `hectordiazgomez`, repository `sol-sdks`, workflow `publish-pypi.yml`, environment `pypi`. Run that workflow manually from `main` with the reviewed version. It verifies the release archives before using short-lived OIDC credentials.
7. Verify registry hashes and install both packages into clean environments. Update website install snippets only after the registry installations pass.

Never put registry tokens in source, logs or command arguments. Publishing success must be verified against each registry; a local build or GitHub release is not registry publication.
