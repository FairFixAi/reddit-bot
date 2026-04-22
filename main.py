"""
Reddit Bot – single entrypoint for production.
Run once on the server; handles collection, classification, retention, and weekly report on schedule.
"""
import logging
import time
from datetime import date, datetime, timezone

from utils.config import (
    FETCH_INTERVAL_MINUTES,
    CLASSIFICATION_INTERVAL_MINUTES,
    RETENTION_RUN_INTERVAL_HOURS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Intervals in seconds
COLLECTION_INTERVAL = FETCH_INTERVAL_MINUTES * 60
CLASSIFICATION_INTERVAL = CLASSIFICATION_INTERVAL_MINUTES * 60
RETENTION_INTERVAL = RETENTION_RUN_INTERVAL_HOURS * 60 * 60

# Last run timestamps (0 = run soon)
_last_collection = 0.0
_last_classification = 0.0
_last_retention = 0.0
# Weekly report: only on Monday (UTC); last date we sent so we send at most once per Monday
_last_weekly_report_date: date | None = None


def _run_collection() -> None:
    from jobs.run_collection import run_once
    try:
        n = run_once()
        logger.info("Collection: %d new posts stored", n)
    except Exception as e:
        logger.exception("Collection failed: %s", e)


def _run_classification() -> None:
    try:
        from jobs.run_classification import main as classification_main
        classification_main()
    except Exception as e:
        logger.exception("Classification failed: %s", e)


def _run_retention() -> None:
    try:
        from jobs.run_retention import main as retention_main
        retention_main()
    except Exception as e:
        logger.exception("Retention failed: %s", e)


def _run_weekly_report() -> None:
    try:
        from jobs.weekly_report import main as report_main
        report_main()
    except Exception as e:
        logger.exception("Weekly report failed: %s", e)


def main() -> None:
    global _last_collection, _last_classification, _last_retention, _last_weekly_report_date
    logger.info(
        "Reddit Bot started. Collection every %s min, classification every %s min, retention daily, report on Mondays only.",
        FETCH_INTERVAL_MINUTES,
        CLASSIFICATION_INTERVAL_MINUTES,
    )
    while True:
        now = time.time()
        if now - _last_collection >= COLLECTION_INTERVAL:
            _run_collection()
            _last_collection = now
        if now - _last_classification >= CLASSIFICATION_INTERVAL:
            _run_classification()
            _last_classification = now
        if now - _last_retention >= RETENTION_INTERVAL:
            _run_retention()
            _last_retention = now
        # Weekly report: only on Monday (UTC), at most once per Monday
        today_utc = datetime.now(timezone.utc).date()
        if today_utc.weekday() == 0 and _last_weekly_report_date != today_utc:
            _run_weekly_report()
            _last_weekly_report_date = today_utc
        time.sleep(60)


if __name__ == "__main__":
    main()
