from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, literal_column, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.schemas import (
    CompanyCount,
    FilterCount,
    FilterOptionsResponse,
    HealthResponse,
    JobListResponse,
    JobResponse,
    JobTypeFilterCount,
)
from app.models import Job, JobStatus, JobType

router = APIRouter()
DbSession = Annotated[Session, Depends(get_db)]
SortOrder = Literal["newest", "oldest", "title_asc", "title_desc"]


def _active_job_filters(
    db: Session,
    *,
    q: str | None,
    city: str | None,
    job_type: JobType | None,
    company: str | None,
) -> list:
    filters = [Job.status == JobStatus.ACTIVE]
    if q:
        if db.get_bind().dialect.name == "postgresql":
            document = func.to_tsvector(
                literal_column("'english'"),
                func.coalesce(Job.title, "")
                + literal_column("' '")
                + func.coalesce(Job.company, "")
                + literal_column("' '")
                + func.coalesce(Job.description, ""),
            )
            filters.append(
                document.bool_op("@@")(
                    func.plainto_tsquery(literal_column("'english'"), q)
                )
            )
        else:
            pattern = f"%{q}%"
            filters.append(
                or_(
                    Job.title.ilike(pattern),
                    Job.company.ilike(pattern),
                    Job.description.ilike(pattern),
                )
            )
    if city:
        filters.append(Job.city.ilike(city))
    if job_type is not None:
        filters.append(Job.job_type == job_type)
    if company:
        filters.append(Job.company.ilike(company))
    return filters


@router.get("/health", response_model=HealthResponse)
def health(db: DbSession) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from error
    return HealthResponse(ok=True, database="connected")


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    db: DbSession,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    city: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    job_type: JobType | None = None,
    company: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=50)] = 20,
    sort: SortOrder = "newest",
) -> JobListResponse:
    filters = _active_job_filters(
        db,
        q=q,
        city=city,
        job_type=job_type,
        company=company,
    )
    total = db.scalar(select(func.count()).select_from(Job).where(*filters)) or 0
    statement = select(Job).where(*filters)

    if sort == "newest":
        statement = statement.order_by(Job.posted_at.desc().nullslast(), Job.id.desc())
    elif sort == "oldest":
        statement = statement.order_by(Job.posted_at.asc().nullsfirst(), Job.id.asc())
    elif sort == "title_asc":
        statement = statement.order_by(Job.title.asc(), Job.id.asc())
    else:
        statement = statement.order_by(Job.title.desc(), Job.id.desc())

    jobs = db.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all()
    return JobListResponse(items=jobs, total=total, page=page, page_size=page_size)


@router.get("/jobs/{slug}", response_model=JobResponse)
def get_job(slug: str, db: DbSession) -> JobResponse:
    job = db.scalar(select(Job).where(Job.slug == slug).limit(1))
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    if job.status == JobStatus.EXPIRED:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This job has expired",
        )
    return JobResponse.model_validate(job)


@router.get("/companies", response_model=list[CompanyCount])
def list_companies(db: DbSession) -> list[CompanyCount]:
    rows = db.execute(
        select(Job.company, func.count(Job.id).label("active_jobs"))
        .where(Job.status == JobStatus.ACTIVE)
        .group_by(Job.company)
        .order_by(func.count(Job.id).desc(), Job.company.asc())
    ).all()
    return [
        CompanyCount(company=company, active_jobs=count)
        for company, count in rows
    ]


@router.get("/meta/filters", response_model=FilterOptionsResponse)
def list_filter_options(db: DbSession) -> FilterOptionsResponse:
    city_rows = db.execute(
        select(Job.city, func.count(Job.id))
        .where(Job.status == JobStatus.ACTIVE, Job.city.is_not(None))
        .group_by(Job.city)
        .order_by(Job.city.asc())
    ).all()
    job_type_rows = db.execute(
        select(Job.job_type, func.count(Job.id))
        .where(Job.status == JobStatus.ACTIVE)
        .group_by(Job.job_type)
        .order_by(Job.job_type.asc())
    ).all()
    return FilterOptionsResponse(
        cities=[FilterCount(value=city, count=count) for city, count in city_rows],
        job_types=[
            JobTypeFilterCount(job_type=job_type, count=count)
            for job_type, count in job_type_rows
        ],
    )
