"""
Run AI classification on posts that don't have a classification yet.
Run periodically (e.g. after each collection or on a schedule).
"""
import logging
import sys

from utils.config import (
    CLASSIFICATION_BATCH_SIZE,
    CLASSIFICATION_MAX_SELFTEXT_CHARS,
    OPENAI_API_KEY,
)
from data.db import get_posts_without_classification, insert_classification
from jobs.classifier import classify_post

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set in .env")
        sys.exit(1)
    posts = get_posts_without_classification(limit=CLASSIFICATION_BATCH_SIZE)
    if not posts:
        logger.info("No unclassified posts")
        return
    logger.info("Classifying %d post(s) (batch limit %s)", len(posts), CLASSIFICATION_BATCH_SIZE)
    for p in posts:
        try:
            body = p["selftext"] or ""
            if CLASSIFICATION_MAX_SELFTEXT_CHARS and len(body) > CLASSIFICATION_MAX_SELFTEXT_CHARS:
                body = body[: CLASSIFICATION_MAX_SELFTEXT_CHARS]
            row = classify_post(
                title=p["title"] or "",
                selftext=body,
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
        except Exception as e:
            logger.exception("Failed to classify post_id=%s: %s", p["id"], e)
    logger.info("Classification run complete")


if __name__ == "__main__":
    main()
