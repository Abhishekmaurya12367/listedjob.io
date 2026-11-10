from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.ingest.fetchers import fetch_jobs
from app.ingest.config import load_companies, load_tech_keywords
from app.ingest.normalize import (
    is_india_location,
    is_tech_role,
    normalize_job,
)
from app.ingest.service import ingest_company
from app.models import Job, JobStatus, JobType

TECH_KEYWORDS = [
    "software",
    "software engineer",
    "developer",
    "machine learning",
]


def test_loads_company_slugs_and_tech_keywords(tmp_path):
    companies_path = tmp_path / "companies.yaml"
    companies_path.write_text(
        "greenhouse:\n  - acme\nlever:\n  - example-inc\n",
        encoding="utf-8",
    )
    keywords_path = tmp_path / "tech.yaml"
    keywords_path.write_text("keywords:\n  - software\n", encoding="utf-8")

    assert load_companies(companies_path) == {
        "greenhouse": ["acme"],
        "lever": ["example-inc"],
    }
    assert load_tech_keywords(keywords_path) == ["software"]


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_greenhouse_fetch_and_normalize():
    payload = {
        "jobs": [
            {
                "id": 101,
                "title": "Software Engineer Intern",
                "company_name": "Acme",
                "location": {"name": "Bengaluru, India"},
                "absolute_url": "https://example.test/jobs/101",
                "first_published": "2025-01-02T03:04:05Z",
                "content": "<p>Build <b>software</b> tools &amp; systems.</p>",
            }
        ]
    }

    def handler(request):
        assert str(request.url) == (
            "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
        )
        return httpx.Response(200, json=payload, request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )
    try:
        jobs = fetch_jobs(client, "greenhouse", "acme", sleep=lambda _: None)
    finally:
        client.close()

    normalized = normalize_job("greenhouse", jobs[0], "acme", TECH_KEYWORDS)
    assert normalized is not None
    assert normalized.external_id == "101"
    assert normalized.description == "Build software tools & systems."
    assert normalized.city == "Bengaluru"
    assert normalized.job_type is JobType.INTERNSHIP
    assert normalized.posted_at == datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert "software-engineer-intern-acme-101" in normalized.slug


@pytest.mark.parametrize("word", ["intern", "internship", "trainee", "fresher"])
def test_internship_keywords(word):
    normalized = normalize_job(
        "greenhouse",
        {
            "id": word,
            "title": f"Software Engineer {word}",
            "location": {"name": "Bengaluru, India"},
        },
        "acme",
        TECH_KEYWORDS,
    )
    assert normalized is not None
    assert normalized.job_type is JobType.INTERNSHIP


def test_lever_fetch_and_normalize():
    payload = [
        {
            "id": "lever-1",
            "text": "Backend Developer",
            "categories": {"location": "Remote - India"},
            "description": "<div>Develop APIs in Python.</div>",
            "hostedUrl": "https://example.test/jobs/lever-1",
            "createdAt": 1735787045000,
        }
    ]

    def handler(request):
        assert str(request.url) == "https://api.lever.co/v0/postings/acme?mode=json"
        return httpx.Response(200, json=payload, request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )
    try:
        jobs = fetch_jobs(client, "lever", "acme", sleep=lambda _: None)
    finally:
        client.close()

    normalized = normalize_job("lever", jobs[0], "acme", TECH_KEYWORDS)
    assert normalized is not None
    assert normalized.external_id == "lever-1"
    assert normalized.location == "Remote - India"
    assert normalized.city is None
    assert normalized.description == "Develop APIs in Python."
    assert normalized.apply_url == "https://example.test/jobs/lever-1"
    assert normalized.job_type is JobType.FULL_TIME
    assert normalized.posted_at == datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_fetch_retries_transient_http_error():
    calls = 0
    delays = []

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"jobs": []}, request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        jobs = fetch_jobs(
            client,
            "greenhouse",
            "acme",
            max_retries=2,
            backoff_seconds=0.25,
            sleep=delays.append,
        )
    finally:
        client.close()

    assert jobs == []
    assert calls == 2
    assert delays == [0.25]


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("Remote - India", True),
        ("Bengaluru, Karnataka", True),
        ("New Delhi, India", True),
        ("Remote - US", False),
        ("London, United Kingdom", False),
        (None, False),
    ],
)
def test_india_location_filter(location, expected):
    assert is_india_location(location) is expected


def test_tech_role_filter():
    assert is_tech_role("Software Engineer", None, TECH_KEYWORDS)
    assert is_tech_role("Analyst", "Machine learning model operations", TECH_KEYWORDS)
    assert not is_tech_role(
        "Finance Associate", "Manage quarterly accounts", TECH_KEYWORDS
    )


def test_fetch_failure_does_not_expire_company_jobs(session_factory):
    with session_factory.begin() as session:
        session.add(
            Job(
                source="greenhouse",
                external_id="old-1",
                title="Software Engineer",
                company="Acme",
                location="Bengaluru",
                city="Bengaluru",
                job_type=JobType.FULL_TIME,
                description="Build software",
                apply_url="https://example.test/old",
                status=JobStatus.ACTIVE,
                slug="software-engineer-acme-old-1",
            )
        )

    def fail_request(request):
        return httpx.Response(503, request=request)

    client = httpx.Client(transport=httpx.MockTransport(fail_request))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            ingest_company(
                client,
                "greenhouse",
                "acme",
                session_factory,
                TECH_KEYWORDS,
                max_retries=1,
                backoff_seconds=0,
                sleep=lambda _: None,
            )
    finally:
        client.close()

    with session_factory() as session:
        job = session.scalar(select(Job).where(Job.external_id == "old-1"))
        assert job is not None
        assert job.status is JobStatus.ACTIVE


def test_success_expires_only_jobs_missing_from_source(session_factory):
    with session_factory.begin() as session:
        for external_id in ("existing", "excluded", "stale"):
            session.add(
                Job(
                    source="greenhouse",
                    external_id=external_id,
                    title="Software Engineer",
                    company="Acme",
                    location="Bengaluru",
                    city="Bengaluru",
                    job_type=JobType.FULL_TIME,
                    description="Build software",
                    apply_url="https://example.test/job",
                    status=JobStatus.ACTIVE,
                    slug=f"software-engineer-acme-{external_id}",
                )
            )

    payload = {
        "jobs": [
            {
                "id": "existing",
                "title": "Software Engineer",
                "location": {"name": "Bengaluru, India"},
                "content": "<p>Build software.</p>",
                "absolute_url": "https://example.test/existing",
            },
            {
                "id": "excluded",
                "title": "Finance Associate",
                "location": {"name": "New York, USA"},
                "content": "Finance",
            },
            {
                "id": "new",
                "title": "Software Engineer II",
                "location": {"name": "Pune, India"},
                "content": "<p>Build software.</p>",
                "absolute_url": "https://example.test/new",
            }
        ]
    }
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload, request=request)
        )
    )
    try:
        stats = ingest_company(
            client,
            "greenhouse",
            "acme",
            session_factory,
            TECH_KEYWORDS,
            sleep=lambda _: None,
        )
    finally:
        client.close()

    assert (
        stats.fetched,
        stats.kept,
        stats.inserted,
        stats.updated,
        stats.expired,
    ) == (3, 2, 1, 1, 1)
    with session_factory() as session:
        jobs = {
            job.external_id: job.status
            for job in session.scalars(select(Job)).all()
        }
    assert jobs["existing"] is JobStatus.ACTIVE
    assert jobs["excluded"] is JobStatus.ACTIVE
    assert jobs["stale"] is JobStatus.EXPIRED
    assert jobs["new"] is JobStatus.ACTIVE
