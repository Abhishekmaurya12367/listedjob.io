from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPANIES_PATH = PROJECT_ROOT / "companies.yaml"
TECH_KEYWORDS_PATH = PROJECT_ROOT / "tech_keywords.yaml"


def _read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_companies(path: Path = COMPANIES_PATH) -> dict[str, list[str]]:
    config = _read_yaml(path)
    if not isinstance(config, dict):
        raise ValueError(f"{path} must contain a mapping of sources to slug lists")

    companies: dict[str, list[str]] = {}
    for source in ("greenhouse", "lever"):
        slugs = config.get(source, [])
        if not isinstance(slugs, list) or any(
            not isinstance(slug, str) or not slug.strip() for slug in slugs
        ):
            raise ValueError(f"{source} in {path} must be a list of non-empty slugs")
        companies[source] = [slug.strip() for slug in slugs]
    return companies


def load_tech_keywords(path: Path = TECH_KEYWORDS_PATH) -> list[str]:
    config = _read_yaml(path)
    keywords = config.get("keywords") if isinstance(config, dict) else None
    if not isinstance(keywords, list) or any(
        not isinstance(keyword, str) or not keyword.strip() for keyword in keywords
    ):
        raise ValueError(f"{path} must contain a 'keywords' list of non-empty strings")
    return [keyword.strip() for keyword in keywords]
