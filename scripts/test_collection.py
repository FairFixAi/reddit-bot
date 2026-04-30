"""
Test script: run one collection cycle (RSS or API) and report how many posts were inserted.
Does not change production; uses same logic as jobs.run_collection.run_once.
"""
import logging
import sys

from jobs.run_collection import run_once
from utils.pipeline_control import ensure_pipeline_enabled

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    ensure_pipeline_enabled()
    logger.info("Running one collection cycle (test)...")
    try:
        n = run_once()
        logger.info("Test collection OK: %d new posts inserted", n)
    except Exception as e:
        logger.exception("Collection failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
