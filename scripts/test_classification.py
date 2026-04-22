"""
Test script: run classification on a small batch of unclassified posts (limit 2).
Uses OPENAI_API_KEY from .env. No email; just logs results.
"""
import logging
import sys

from data.db import get_posts_without_classification, insert_classification
from jobs.classifier import classify_post

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

TEST_LIMIT = 2


def main() -> None:
    posts = get_posts_without_classification(limit=TEST_LIMIT)
    if not posts:
        logger.info("No unclassified posts; nothing to test")
        return
    logger.info("Test classification: %d post(s)", len(posts))
    for p in posts:
        try:
            row = classify_post(
                title=p["title"] or "",
                selftext=p["selftext"] or "",
                subreddit=p["subreddit"] or "",
            )
            insert_classification(
                post_id=p["id"],
                topic=row.get("topic"),
                sentiment=row.get("sentiment"),
                emotional_intensity=row.get("emotional_intensity"),
                financial_mention=row.get("financial_mention"),
                financial_amount=row.get("financial_amount"),
                problem_category=row.get("problem_category"),
                intent=row.get("intent"),
                vehicle_make=row.get("vehicle_make"),
                vehicle_model=row.get("vehicle_model"),
                keywords=row.get("keywords"),
                summary=row.get("summary"),
                suggested_action=row.get("suggested_action"),
            )
            logger.info("Classified post_id=%s -> topic=%s sentiment=%s", p["id"], row.get("topic"), row.get("sentiment"))
        except Exception as e:
            logger.exception("Failed to classify post_id=%s: %s", p["id"], e)
            sys.exit(1)
    logger.info("Test classification complete")


if __name__ == "__main__":
    main()
