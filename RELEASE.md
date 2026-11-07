# Release 0.1.0

Python distribution: `buildsol-0.1.0-py3-none-any.whl` and `buildsol-0.1.0.tar.gz`.
Node distribution: `buildsol-0.1.0.tgz`.

Build and validate from a clean checkout:

```sh
python -m pip install build twine
python -m build python
python -m twine check python/dist/*
cd javascript
npm ci
npm run typecheck
npm test
npm pack
```

Registry publication is pending the owner's npm/PyPI access. After authentication, check that version 0.1.0 does not already exist, inspect these exact artifacts and publish:

```sh
# In javascript/, after npm login (may require account MFA):
npm publish buildsol-0.1.0.tgz --access public
# From the repository root, with PyPI authentication configured outside source:
python -m twine upload python/dist/*
```

Never include tokens in command arguments or the repository. Use interactive login, an approved credential store or trusted publishing. A successful local build, GitHub upload or dry run is not a successful registry publication. Verify both public registries by installing into clean environments. Only then switch website install snippets to `pip install buildsol` / `npm install buildsol` and remove the pending-registry notice.
