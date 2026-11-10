from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.db.base import Base
from app.main import app
from app.models import Job, JobStatus, JobType


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    def override_get_db():
        with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with test_session_factory.begin() as session:
        session.add_all(
            [
                Job(
                    source="greenhouse",
                    external_id="acme-1",
                    title="Senior Python Engineer",
                    company="Acme",
                    location="Bengaluru, India",
                    city="Bengaluru",
                    job_type=JobType.FULL_TIME,
                    description="Build Python services and APIs.",
                    apply_url="https://example.test/acme-1",
                    posted_at=datetime(2025, 1, 3, tzinfo=timezone.utc),
                    status=JobStatus.ACTIVE,
                    slug="senior-python-engineer-acme-acme-1",
                ),
                Job(
                    source="greenhouse",
                    external_id="acme-2",
                    title="Data Intern",
                    company="Acme",
                    location="Bangalore, India",
                    city="Bengaluru",
                    job_type=JobType.INTERNSHIP,
                    description="Machine learning and analytics.",
                    apply_url="https://example.test/acme-2",
                    posted_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
                    status=JobStatus.ACTIVE,
                    slug="data-intern-acme-acme-2",
                ),
                Job(
                    source="lever",
                    external_id="beta-1",
                    title="Software Developer",
                    company="Beta",
                    location="Mumbai, India",
                    city="Mumbai",
                    job_type=JobType.FULL_TIME,
                    description="Develop cloud software.",
                    apply_url="https://example.test/beta-1",
                    posted_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                    status=JobStatus.ACTIVE,
                    slug="software-developer-beta-beta-1",
                ),
                Job(
                    source="lever",
                    external_id="acme-old",
                    title="Expired Python Engineer",
                    company="Acme",
                    location="Hyderabad, India",
                    city="Hyderabad",
                    job_type=JobType.FULL_TIME,
                    description="Expired Python role.",
                    apply_url="https://example.test/acme-old",
                    posted_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                    status=JobStatus.EXPIRED,
                    slug="expired-python-engineer-acme-acme-old",
                ),
            ]
        )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_health_checks_database(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "database": "connected"}


def test_job_filters_and_expired_jobs_are_hidden(client):
    response = client.get(
        "/jobs",
        params={
            "city": "Bengaluru",
            "job_type": "internship",
            "company": "Acme",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 1
    assert [job["slug"] for job in result["items"]] == ["data-intern-acme-acme-2"]

    all_jobs = client.get("/jobs").json()
    assert all_jobs["total"] == 3
    assert all(job["status"] == "active" for job in all_jobs["items"])
    assert not any("expired" in job["slug"] for job in all_jobs["items"])


def test_job_pagination_and_newest_sort(client):
    first_page = client.get("/jobs", params={"page": 1, "page_size": 2})
    second_page = client.get("/jobs", params={"page": 2, "page_size": 2})
    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert first_page.json()["page"] == 1
    assert first_page.json()["page_size"] == 2
    assert [job["external_id"] for job in first_page.json()["items"]] == [
        "acme-1",
        "acme-2",
    ]
    assert [job["external_id"] for job in second_page.json()["items"]] == ["beta-1"]


def test_job_search_matches_title_company_and_description(client):
    for query, expected_slug in [
        ("Python", "senior-python-engineer-acme-acme-1"),
        ("Acme", "senior-python-engineer-acme-acme-1"),
        ("analytics", "data-intern-acme-acme-2"),
        ("cloud", "software-developer-beta-beta-1"),
    ]:
        response = client.get("/jobs", params={"q": query})
        assert response.status_code == 200
        assert expected_slug in [job["slug"] for job in response.json()["items"]]


@pytest.mark.parametrize(
    "params",
    [
        {"page": 0},
        {"page_size": 0},
        {"page_size": 51},
        {"job_type": "contract"},
        {"sort": "relevance"},
    ],
)
def test_invalid_job_query_params_return_422(client, params):
    assert client.get("/jobs", params=params).status_code == 422


def test_job_detail_distinguishes_expired_and_missing(client):
    expired = client.get("/jobs/expired-python-engineer-acme-acme-old")
    missing = client.get("/jobs/not-a-real-job")
    assert expired.status_code == 410
    assert expired.json() == {"detail": "This job has expired"}
    assert missing.status_code == 404


def test_companies_and_filter_metadata_only_count_active_jobs(client):
    companies = client.get("/companies")
    assert companies.status_code == 200
    assert companies.json() == [
        {"company": "Acme", "active_jobs": 2},
        {"company": "Beta", "active_jobs": 1},
    ]

    filters = client.get("/meta/filters")
    assert filters.status_code == 200
    assert filters.json() == {
        "cities": [
            {"value": "Bengaluru", "count": 2},
            {"value": "Mumbai", "count": 1},
        ],
        "job_types": [
            {"job_type": "full-time", "count": 2},
            {"job_type": "internship", "count": 1},
        ],
    }
