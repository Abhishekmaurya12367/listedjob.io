from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import re
from typing import Any

from app.models import JobType

INDIAN_CITIES = (
    "New Delhi",
    "Bengaluru",
    "Bangalore",
    "Hyderabad",
    "Ahmedabad",
    "Thiruvananthapuram",
    "Visakhapatnam",
    "Bhubaneswar",
    "Chandigarh",
    "Coimbatore",
    "Gurugram",
    "Gurgaon",
    "Kolkata",
    "Lucknow",
    "Mumbai",
    "Mysuru",
    "Mysore",
    "Nagpur",
    "Noida",
    "Pune",
    "Jaipur",
    "Indore",
    "Surat",
    "Vadodara",
    "Kochi",
    "Chennai",
    "Delhi",
)
INDIA_PATTERN = re.compile(
    r"\bindia\b|"
    + "|".join(
        rf"(?<!\w){re.escape(city)}(?!\w)"
        for city in sorted(INDIAN_CITIES, key=len, reverse=True)
    ),
    re.IGNORECASE,
)
INTERNSHIP_PATTERN = re.compile(r"\bintern(?:ship)?\b|\btrainee\b|\bfresher\b", re.I)
SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "address",
        "article",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "p",
        "section",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden_depth += 1
        elif tag in self.BLOCK_TAGS and not self.hidden_depth:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif tag in self.BLOCK_TAGS and not self.hidden_depth:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


@dataclass(frozen=True)
class NormalizedJob:
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
    slug: str

    def as_model_values(self) -> dict[str, Any]:
        return {
            "external_id": self.external_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "city": self.city,
            "job_type": self.job_type,
            "description": self.description,
            "apply_url": self.apply_url,
            "posted_at": self.posted_at,
            "valid_through": self.valid_through,
            "slug": self.slug,
        }


def strip_html(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    text = re.sub(r"\s+", " ", "".join(parser.parts)).strip()
    return text or None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _slug_part(value: str) -> str:
    return SLUG_PATTERN.sub("-", value.lower()).strip("-")


def company_name_from_slug(company_slug: str) -> str:
    return company_slug.replace("-", " ").title()


def make_slug(title: str, company: str, external_id: str, source: str) -> str:
    components = [_slug_part(value) for value in (title, company, external_id)]
    base = "-".join(part for part in components if part) or "job"
    digest = sha256(
        "\0".join((title, company, external_id, source)).encode("utf-8")
    ).hexdigest()[:12]
    max_base_length = 255 - len(digest) - 1
    return f"{base[:max_base_length].rstrip('-')}-{digest}"


def _field_value(job: dict[str, Any], key: str) -> str | None:
    value = job.get(key)
    if isinstance(value, dict):
        value = value.get("name")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _job_fields(
    source: str, raw: dict[str, Any], company_slug: str
) -> dict[str, Any] | None:
    if source == "greenhouse":
        location = _field_value(raw, "location")
        description = strip_html(raw.get("content"))
        title = _field_value(raw, "title")
        external_id = _field_value(raw, "id")
        apply_url = _field_value(raw, "absolute_url")
        posted_at = _parse_datetime(raw.get("first_published") or raw.get("updated_at"))
    elif source == "lever":
        categories = raw.get("categories")
        categories = categories if isinstance(categories, dict) else {}
        location = _field_value(categories, "location")
        description = strip_html(raw.get("description") or raw.get("descriptionPlain"))
        title = _field_value(raw, "text")
        external_id = _field_value(raw, "id")
        apply_url = _field_value(raw, "applyUrl") or _field_value(raw, "hostedUrl")
        posted_at = _parse_datetime(raw.get("createdAt"))
    else:
        raise ValueError(f"Unsupported job source: {source}")

    if not external_id or not title:
        return None

    company = company_name_from_slug(company_slug)
    location = location[:255] if location else None
    search_text = f"{title} {description or ''}"
    internship = bool(INTERNSHIP_PATTERN.search(search_text))
    return {
        "external_id": external_id,
        "title": title[:255],
        "company": company[:255],
        "location": location,
        "city": _match_city(location),
        "job_type": JobType.INTERNSHIP if internship else JobType.FULL_TIME,
        "description": description,
        "apply_url": apply_url,
        "posted_at": posted_at,
        "valid_through": _parse_datetime(
            raw.get("valid_through") or raw.get("validThrough")
        ),
    }


def _match_city(location: str | None) -> str | None:
    if not location:
        return None
    return next(
        (
            city
            for city in sorted(INDIAN_CITIES, key=len, reverse=True)
            if re.search(rf"(?<!\w){re.escape(city)}(?!\w)", location, re.I)
        ),
        None,
    )


def is_india_location(location: str | None) -> bool:
    return bool(location and INDIA_PATTERN.search(location))


def is_tech_role(title: str, description: str | None, keywords: list[str]) -> bool:
    text = f"{title} {description or ''}"
    return any(
        re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text, re.I)
        for keyword in keywords
    )


def normalize_job(
    source: str,
    raw: dict[str, Any],
    company_slug: str,
    tech_keywords: list[str],
) -> NormalizedJob | None:
    fields = _job_fields(source, raw, company_slug)
    if fields is None:
        return None
    if not is_india_location(fields["location"]):
        return None
    if not is_tech_role(fields["title"], fields["description"], tech_keywords):
        return None

    return NormalizedJob(
        **fields,
        slug=make_slug(
            fields["title"],
            fields["company"],
            fields["external_id"],
            source,
        ),
    )
