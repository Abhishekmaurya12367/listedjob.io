# listedjob.io Backend Specification

## Current stack
- Python 3.11
- FastAPI, SQLAlchemy 2, PostgreSQL 16, Alembic
- `httpx` fetches source job boards; PyYAML loads ingestion configuration
- Docker Compose runs local PostgreSQL with persistent volume `postgres_data`
- `DATABASE_URL` can override the local PostgreSQL connection URL

## Jobs table
- `id`: integer primary key
- `source`: required string (100)
- `external_id`: required string (255)
- Unique constraint on `(source, external_id)`
- `title`, `company`: required strings (255)
- `location`: optional string (255); `city`: optional string (100)
- `job_type`: required PostgreSQL enum: `internship`, `full-time`
- `description`, `apply_url`: optional text
- `posted_at`, `valid_through`: optional timezone-aware timestamps
- `status`: PostgreSQL enum `active`/`expired`, defaults to `active`
- `slug`: required string (255)

## Ingestion
- Add Greenhouse and Lever board slugs to their lists in `companies.yaml`.
- `python -m app.ingest run` fetches configured boards.
- Greenhouse uses the boards API with job content; Lever uses its postings API.
- HTTP requests use a 15-second timeout, retries with exponential backoff, and
  a one-second delay between companies.
- Jobs are upserted by `(source, external_id)`; a successful company fetch
  expires active jobs missing from that source response. Failed fetches do not
  trigger expiry.
- HTML descriptions are converted to plain text. Job type uses internship,
  intern, trainee, and fresher keyword rules.
- Only India locations and tech roles matching `tech_keywords.yaml` are kept.
- City matching uses a built-in list of common Indian cities.
- Per-company logs report fetched, kept, inserted, updated, and expired counts.

## Local run and verification
1. Start PostgreSQL: `docker compose up -d db`
2. Create and activate a Python 3.11 virtual environment.
3. Install: `python -m pip install -e ".[dev]"`
4. Apply migrations: `alembic upgrade head`
5. Ingest configured jobs: `python -m app.ingest run`
6. Inspect data: `docker compose exec db psql -U listedjob -d listedjob`
7. Run tests: `python -m pytest`
