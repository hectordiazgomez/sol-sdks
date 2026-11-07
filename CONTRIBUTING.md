# Contributing

Use Python 3.10+ and Node.js 20+. No real API key is needed for automated tests.

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e './python[dev]'
pytest python/tests
mypy python/src/buildsol
ruff check python/src --select F,I
cd javascript
npm ci
npm run typecheck
npm test
```

Keep the Python sync/async and JavaScript APIs aligned. Add contract tests for new endpoints, cleanup on cancellation, authentication, byte preservation and billing-safe retries. Do not add automatic retries to operations that lack server idempotency. Never commit credentials, real customer audio, generated audio or private server configuration.

Version both packages together. Run `python -m build python` and `npm pack` in `javascript/`, inspect package contents, install both in clean environments and run the examples against a local test server before releasing. Public network smoke tests must use an explicitly selected test account, tiny inputs and documented usage. Do not clone or delete real voices as part of a smoke test.

Publish registry packages only after account authorization is configured. Do not overwrite an existing version. GitHub release assets include SHA256SUMS. See RELEASE.md.
