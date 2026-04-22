"""
Reddit Bot – single entrypoint for production.

Each process runs **one** cycle (collection → classification → retention) and **exits**.
Use **Render Cron Jobs** (or another scheduler) to invoke `python main.py` on your desired cadence so
memory is released between runs.

Weekly email is **not** included here (would repeat if this job ran every few minutes on Monday).
Schedule `python -m jobs.weekly_report` separately (e.g. once per Monday UTC). See README and `render.yaml`.
"""
from __future__ import annotations

import logging

from utils.config import CLASSIFICATION_INTERVAL_MINUTES, FETCH_INTERVAL_MINUTES

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


def main() -> None:
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
    logger.info("Reddit Bot single run finished; exiting.")


if __name__ == "__main__":
    main()
