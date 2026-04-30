"""
Run 90-day rolling retention: delete posts (and their classifications) older than RETENTION_DAYS.
Run daily or weekly (e.g. via cron).
"""
import logging
import sys

from utils.config import RETENTION_DAYS
from utils.pipeline_control import ensure_pipeline_enabled
from data.db import delete_posts_older_than_days

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    ensure_pipeline_enabled()
    deleted = delete_posts_older_than_days(RETENTION_DAYS)
    logger.info("Retention complete: %d posts removed (older than %s days)", deleted, RETENTION_DAYS)


if __name__ == "__main__":
    main()
