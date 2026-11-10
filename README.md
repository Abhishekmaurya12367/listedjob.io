# listedjob.io backend (Task 1)

Minimal FastAPI, SQLAlchemy, and Alembic scaffold for the `jobs` table. Python
3.11 is required. The initial migration creates the table and the unique
`(source, external_id)` constraint.

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

## Verify

Check the applied migration:

```powershell
alembic current
```

Confirm the table and unique constraint exist in PostgreSQL:

```powershell
docker compose exec db psql -U listedjob -d listedjob -c "\d jobs"
```

The table has PostgreSQL enum types for `job_type` (`internship`, `full-time`)
and `status` (`active`, `expired`); new rows default to `active`.
