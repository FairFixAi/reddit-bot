"""
Test script: run retention (delete posts older than RETENTION_DAYS).
Same behavior as production jobs.run_retention.
"""
import logging
import sys

from utils.config import RETENTION_DAYS
from data.db import delete_posts_older_than_days
from utils.pipeline_control import ensure_pipeline_enabled

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    ensure_pipeline_enabled()
    logger.info("Running retention: deleting posts older than %s days", RETENTION_DAYS)
    deleted = delete_posts_older_than_days(RETENTION_DAYS)
    logger.info("Retention complete: %d posts removed", deleted)


if __name__ == "__main__":
    main()
