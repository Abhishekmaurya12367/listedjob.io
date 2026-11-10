import argparse
import logging

from app.db.session import SessionLocal
from app.ingest.service import run_ingestion


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest jobs from configured boards")
    parser.add_argument("command", choices=["run"])
    parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_ingestion(SessionLocal)


if __name__ == "__main__":
    main()
