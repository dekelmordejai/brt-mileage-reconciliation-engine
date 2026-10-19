# Run the synthetic demonstration

Requirements: Python 3.12 recommended; Python 3.11–3.13 is checked by CI. Node 22+ and a Playwright browser are only needed for browser tests. The UI is in Spanish.

## Windows

```powershell
.\scripts\start.ps1 -Demo
```

## Linux / macOS

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
export MOTOR_DB=private_data/demo.sqlite3
python -m app.cli demo
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Initialize the demo only once in an empty database. Open http://127.0.0.1:8000. Demo users `demo-admin`, `demo-analista` and `demo-revisor` share the demo-only password `Demo-local-2026!`. Never load actual information into a database with these public demo accounts.

## Walkthrough

1. Sign in as `demo-admin`. Open **Fuentes e importación** and process the preloaded synthetic sources.
2. Inspect the four synthetic trips. Reported physical mileage remains distinct from reviewed and economically eligible mileage.
3. Open **Mesa de análisis**, search `DEMO-001`, open the first trip and inspect its source row and checkpoint candidate.
4. Propose a measured segment with origin/destination, supporting evidence, rationale and a synthetic document reference. Submit for review.
5. Sign out; sign in as `demo-revisor`. Review and approve the proposal with a reason. The proposer cannot approve their own decision.
6. Sign back in as `demo-admin` and process again. The new snapshot incorporates the decision; the previous snapshot is unchanged.
7. Export Excel and inspect the audit log. Try an unresolved cross-company trip or an event hold: physical mileage is retained while economic eligibility remains pending.

## Docker, localhost only

```sh
docker compose build
docker compose run --rm motor python -m app.cli demo
docker compose up -d
```

The named volume stores demo state and the published port is restricted to 127.0.0.1:8000. The image uses a non-root account. This does not publish a website. Do not expose it externally without a separate security/deployment review.

## Browser acceptance

Initialize a separate empty demo database and run a server on localhost:8766, then:

```sh
npm ci
npx playwright install chromium
npm run test:e2e
```

`MOTOR_TEST_URL` can select another local test server. On a workstation with Edge installed, `MOTOR_BROWSER_CHANNEL=msedge` uses that browser. The test modifies only the demo database, downloads a synthetic spreadsheet and captures synthetic desktop/mobile screenshots in ignored `test-results/`.

## Backup

```sh
python scripts/backup.py private_data/demo.sqlite3 private_data/demo-backup.sqlite3
```

The backup command uses SQLite's consistent backup API and checks integrity. Never commit database files or credentials. The server does not automatically create users on startup; a non-demo installation must create an administrator with `python -m app.cli user administrator` and a unique password.
