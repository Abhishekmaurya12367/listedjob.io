from dataclasses import dataclass
import logging
import time
from typing import Any, Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.ingest.config import load_companies, load_tech_keywords
from app.ingest.fetchers import fetch_jobs
from app.ingest.normalize import NormalizedJob, normalize_job
from app.models import Job, JobStatus

LOGGER = logging.getLogger("app.ingest")


@dataclass
class CompanyStats:
    source: str
    company: str
    fetched: int = 0
    kept: int = 0
    inserted: int = 0
    updated: int = 0
    expired: int = 0
    error: str | None = None


def _external_id(source: str, raw: dict[str, Any]) -> str | None:
    value = raw.get("id")
    return str(value).strip() if value is not None and str(value).strip() else None


def _upsert_jobs(
    session: Session,
    source: str,
    jobs: list[NormalizedJob],
) -> tuple[int, int]:
    inserted = 0
    updated = 0
    fields = tuple(NormalizedJob.__dataclass_fields__)[:-1]

    for job in jobs:
        values = job.as_model_values()
        existing = session.scalar(
            select(Job).where(
                Job.source == source,
                Job.external_id == job.external_id,
            )
        )
        if existing is None:
            session.add(Job(source=source, status=JobStatus.ACTIVE, **values))
            inserted += 1
            continue

        changed = False
        for field in fields:
            value = values[field]
            if field == "posted_at" and value is None:
                continue
            if getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True
        if existing.status != JobStatus.ACTIVE:
            existing.status = JobStatus.ACTIVE
            changed = True
        if changed:
            updated += 1

    session.flush()
    return inserted, updated


def ingest_company(
    client: httpx.Client,
    source: str,
    company_slug: str,
    session_factory: sessionmaker[Session],
    tech_keywords: list[str],
    *,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> CompanyStats:
    raw_jobs = fetch_jobs(
        client,
        source,
        company_slug,
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        sleep=sleep,
    )
    stats = CompanyStats(
        source=source,
        company=company_slug,
        fetched=len(raw_jobs),
    )

    seen_ids = {
        external_id
        for raw in raw_jobs
        if (external_id := _external_id(source, raw)) is not None
    }
    normalized_by_id: dict[str, NormalizedJob] = {}
    for raw in raw_jobs:
        normalized = normalize_job(source, raw, company_slug, tech_keywords)
        if normalized is not None:
            normalized_by_id[normalized.external_id] = normalized
    normalized_jobs = list(normalized_by_id.values())
    stats.kept = len(normalized_jobs)

    company_name = company_slug.replace("-", " ").title()
    with session_factory() as session:
        with session.begin():
            stats.inserted, stats.updated = _upsert_jobs(
                session, source, normalized_jobs
            )
            stale_jobs = session.scalars(
                select(Job).where(
                    Job.source == source,
                    Job.company == company_name,
                    Job.status == JobStatus.ACTIVE,
                )
            )
            for job in stale_jobs:
                if job.external_id not in seen_ids:
                    job.status = JobStatus.EXPIRED
                    stats.expired += 1

    return stats


def run_ingestion(
    session_factory: sessionmaker[Session],
    *,
    client: httpx.Client | None = None,
    companies: dict[str, list[str]] | None = None,
    tech_keywords: list[str] | None = None,
    company_delay_seconds: float = 1.0,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger = LOGGER,
) -> list[CompanyStats]:
    companies = companies if companies is not None else load_companies()
    tech_keywords = tech_keywords if tech_keywords is not None else load_tech_keywords()
    owned_client = client is None
    http_client = client or httpx.Client(timeout=15.0, follow_redirects=True)
    stats: list[CompanyStats] = []
    company_count = sum(len(slugs) for slugs in companies.values())
    processed = 0

    try:
        for source in ("greenhouse", "lever"):
            for company_slug in companies.get(source, []):
                processed += 1
                try:
                    company_stats = ingest_company(
                        http_client,
                        source,
                        company_slug,
                        session_factory,
                        tech_keywords,
                        max_retries=max_retries,
                        backoff_seconds=backoff_seconds,
                        sleep=sleep,
                    )
                    stats.append(company_stats)
                    logger.info(
                        "%s/%s fetched=%d kept=%d inserted=%d updated=%d expired=%d",
                        source,
                        company_slug,
                        company_stats.fetched,
                        company_stats.kept,
                        company_stats.inserted,
                        company_stats.updated,
                        company_stats.expired,
                    )
                except Exception as error:
                    stats.append(
                        CompanyStats(
                            source=source,
                            company=company_slug,
                            error=str(error),
                        )
                    )
                    logger.exception(
                        "%s/%s failed; fetched=0 kept=0 inserted=0 updated=0 expired=0",
                        source,
                        company_slug,
                    )

                if processed < company_count and company_delay_seconds > 0:
                    sleep(company_delay_seconds)
    finally:
        if owned_client:
            http_client.close()

    return stats
