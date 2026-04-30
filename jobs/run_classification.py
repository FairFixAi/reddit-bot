"""
Run AI classification on posts that don't have a classification yet.
Run periodically (e.g. after each collection or on a schedule).
"""
import logging
import sys

from utils.config import (
    ALLOW_HISTORICAL_REPROCESSING,
    PROCESSING_WINDOW_DAYS,
    effective_classification_batch_size,
)
from utils.pipeline_control import (
    check_openai_budget,
    ensure_pipeline_enabled,
    record_openai_estimated_spend,
)
from data.db import get_unclassified_posts, insert_classification
from jobs.classifier import classify_post

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    ensure_pipeline_enabled()
    batch_size = effective_classification_batch_size()
    posts = get_unclassified_posts(
        limit=batch_size,
        include_historical=ALLOW_HISTORICAL_REPROCESSING,
        max_age_days=PROCESSING_WINDOW_DAYS,
    )
    if not posts:
        logger.info("No unclassified posts")
        return
    budget = check_openai_budget(len(posts))
    logger.info(
        "Classifying %d post(s) (batch limit %s, estimated OpenAI cost $%.6f, weekly spent $%.6f/$%.6f)",
        len(posts),
        batch_size,
        budget.estimated_cost_usd,
        budget.weekly_spent_usd,
        budget.weekly_budget_usd,
    )
    successful = 0
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
            successful += 1
        except Exception as e:
            logger.exception("Failed to classify post_id=%s: %s", p["id"], e)
    record_openai_estimated_spend(successful)
    logger.info("Classification run complete")


if __name__ == "__main__":
    main()
