# listedjob.io backend

FastAPI, SQLAlchemy, and Alembic scaffold with Greenhouse and Lever job
ingestion and a read-only jobs API. Python 3.11 is required.

## Run PostgreSQL

```powershell
docker compose up -d db
```

If host port `5432` is already in use, select another host port (for example
`5433`) and set the matching database URL in the same PowerShell session:

```powershell
$env:POSTGRES_PORT = "5433"
$env:DATABASE_URL = "postgresql+psycopg://listedjob:listedjob@localhost:5433/listedjob"
docker compose up -d db
```

## Install, migrate, and run API

From the project directory, create and activate a Python 3.11 virtual
environment, then install the project:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

The default database URL in `alembic.ini` matches the default local Docker
Compose port. Set `DATABASE_URL` to override it. Keep the port override above
set in the same PowerShell window when applying migrations and starting the API.

## Read API

- `GET /health` checks the database connection.
- `GET /jobs` lists active jobs. Optional parameters: `q`, `city`, `job_type`,
  `company`, `page`, `page_size` (maximum 50), and `sort` (`newest`, `oldest`,
  `title_asc`, or `title_desc`). Search uses PostgreSQL full-text search.
- `GET /jobs/{slug}` returns a job, `404` if missing, or `410` if expired.
- `GET /companies` lists active job counts by company.
- `GET /meta/filters` lists active city and job-type counts.

Examples from another PowerShell window while Uvicorn is running:

```powershell
curl.exe http://localhost:8000/health
curl.exe "http://localhost:8000/jobs?page=1&page_size=20&sort=newest"
curl.exe "http://localhost:8000/jobs?q=software&city=Bengaluru&job_type=full-time"
curl.exe http://localhost:8000/companies
curl.exe http://localhost:8000/meta/filters
curl.exe http://localhost:8000/jobs/software-engineer-example-123
```

The API list and aggregate endpoints include only active jobs. The search GIN
index and filter/order indexes are created by the second Alembic migration;
run `alembic upgrade head` after updating the code.

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

Run the API and mocked ingestion tests with:

```powershell
python -m pytest
```
