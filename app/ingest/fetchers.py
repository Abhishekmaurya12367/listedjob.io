from typing import Any
from urllib.parse import quote

import httpx


GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
LEVER_URL = "https://api.lever.co/v0/postings/{slug}?mode=json"
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


def fetch_jobs(
    client: httpx.Client,
    source: str,
    slug: str,
    *,
    max_retries: int = 3,
    backoff_seconds: float = 1.0,
    sleep: Any,
) -> list[dict[str, Any]]:
    if source == "greenhouse":
        url = GREENHOUSE_URL.format(slug=quote(slug, safe=""))
    elif source == "lever":
        url = LEVER_URL.format(slug=quote(slug, safe=""))
    else:
        raise ValueError(f"Unsupported job source: {source}")

    for attempt in range(max_retries + 1):
        try:
            response = client.get(url)
            if response.status_code in RETRYABLE_STATUS_CODES:
                response.raise_for_status()
            response.raise_for_status()
            payload = response.json()
            jobs = payload.get("jobs") if source == "greenhouse" else payload
            if not isinstance(jobs, list) or any(
                not isinstance(job, dict) for job in jobs
            ):
                raise ValueError(f"Unexpected {source} jobs response for {slug}")
            return jobs
        except httpx.HTTPStatusError as error:
            if (
                error.response.status_code not in RETRYABLE_STATUS_CODES
                or attempt >= max_retries
            ):
                raise
        except httpx.RequestError:
            if attempt >= max_retries:
                raise

        sleep(backoff_seconds * (2**attempt))

    raise RuntimeError(f"Failed to fetch {source} company {slug}")
