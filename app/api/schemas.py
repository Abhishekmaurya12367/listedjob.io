from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import JobStatus, JobType


class HealthResponse(BaseModel):
    ok: bool
    database: str


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    external_id: str
    title: str
    company: str
    location: str | None
    city: str | None
    job_type: JobType
    description: str | None
    apply_url: str | None
    posted_at: datetime | None
    valid_through: datetime | None
    status: JobStatus
    slug: str


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    page: int
    page_size: int


class CompanyCount(BaseModel):
    company: str
    active_jobs: int


class FilterCount(BaseModel):
    value: str
    count: int


class JobTypeFilterCount(BaseModel):
    job_type: JobType
    count: int


class FilterOptionsResponse(BaseModel):
    cities: list[FilterCount]
    job_types: list[JobTypeFilterCount]
