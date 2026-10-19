# Contributing

Use synthetic examples and a reviewable pull request. Do not upload real operational records or private case studies, including in issue bodies, screenshots and CI artifacts.

```sh
python -m pip install -r requirements-dev.txt
python -m pip install -e .
python -m ruff check app src tests scripts
python -m ruff format --check app src tests scripts
python -m pytest
python -m build
```

For browser tests, initialize a separate empty demo database, run the server on localhost:8766, run `npm ci`, install Chromium with `npx playwright install chromium`, and execute `npm run test:e2e`.

Distinguish observations, candidate associations, approved coverage and economic eligibility. A business-rule change needs rationale, scope and a synthetic regression case. Do not convert an assumption into an automatic financial decision. Public availability is not an open-source license; see LICENSE.md before redistributing or reusing the work.
