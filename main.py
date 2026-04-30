"""
Reddit Bot – single entrypoint for production.

Each process runs **one** cycle (collection → classification → retention) and **exits**.
Use **Render Cron Jobs** (or another scheduler) to invoke `python main.py` on your desired cadence so
memory is released between runs.

Weekly email is included with a DB-backed once-per-week guard, so `main.py` can be scheduled alone.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from utils.config import CLASSIFICATION_INTERVAL_MINUTES, FETCH_INTERVAL_MINUTES
from utils.pipeline_control import ensure_pipeline_enabled

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


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


def _run_weekly_report_if_due() -> None:
    now_utc = datetime.now(timezone.utc)
    if now_utc.weekday() != 0:  # Monday
        return
    iso = now_utc.isocalendar()
    week_key = f"{iso.year}-W{iso.week:02d}"
    try:
        from data.db import claim_weekly_report_slot, release_weekly_report_slot

        if not claim_weekly_report_slot(week_key):
            logger.info("Weekly report already sent for %s; skipping.", week_key)
            return
        from jobs.weekly_report import main as weekly_report_main

        weekly_report_main()
        logger.info("Weekly report completed for %s.", week_key)
    except Exception as e:
        logger.exception("Weekly report failed for %s: %s", week_key, e)
        try:
            release_weekly_report_slot(week_key)
        except Exception as release_err:
            logger.exception("Failed to release weekly report slot for %s: %s", week_key, release_err)


def main() -> None:
    ensure_pipeline_enabled()
    logger.info(
        "Reddit Bot single run starting (collection → classification → retention). "
        "Align your cron schedule with FETCH_INTERVAL_MINUTES=%s and "
        "CLASSIFICATION_INTERVAL_MINUTES=%s in .env.",
        FETCH_INTERVAL_MINUTES,
        CLASSIFICATION_INTERVAL_MINUTES,
    )
    _run_collection()
    _run_classification()
    _run_retention()
    _run_weekly_report_if_due()
    logger.info("Reddit Bot single run finished; exiting.")


if __name__ == "__main__":
    main()
