# listedjob.io backend

FastAPI, SQLAlchemy, and Alembic scaffold with Greenhouse and Lever job
ingestion. Python 3.11 is required.

## Run PostgreSQL

```powershell
docker compose up -d db
```

## Install and migrate

From the project directory, create and activate a Python 3.11 virtual
environment, then install the project:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
alembic upgrade head
```

The default database URL in `alembic.ini` matches the local Docker Compose
database. Set `DATABASE_URL` to override it.

## Configure and run ingestion

Add company board slugs to the `greenhouse` and `lever` lists in
`companies.yaml`. The default lists are empty. Adjust the editable role
keywords in `tech_keywords.yaml`, then run:

```powershell
python -m app.ingest run
```

Ingestion logs fetched, kept, inserted, updated, and expired counts for each
company. A company’s active jobs are expired only when its source fetch
succeeds. Transient request failures are retried with exponential backoff; the
runner pauses one second between companies.

## Verify

Check the applied migration and inspect the jobs table and ingested rows:

```powershell
alembic current
docker compose exec db psql -U listedjob -d listedjob -c "\d jobs"
docker compose exec db psql -U listedjob -d listedjob -c "SELECT source, company, title, status FROM jobs ORDER BY company, title LIMIT 20;"
```

The table has PostgreSQL enum types for `job_type` (`internship`, `full-time`)
and `status` (`active`, `expired`); new rows default to `active`.

Run the mocked ingestion unit tests with:

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```
