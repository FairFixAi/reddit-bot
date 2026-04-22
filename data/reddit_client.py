"""Reddit API client: auth and fetch public posts (optional when using RSS)."""
import logging
from datetime import datetime, timezone

import praw
from praw.models import Submission

from utils.config import (
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_USER_AGENT,
    POSTS_PER_RUN,
    PIPELINE_MAX_BATCH,
    clamp_batch_size,
    get_subreddit_names_for_ingestion,
    reddit_api_credentials_active,
)

logger = logging.getLogger(__name__)
SOURCE = "reddit_api"


def _reddit_client() -> praw.Reddit:
    return praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT,
    )


def _submission_to_row(submission: Submission) -> dict:
    """Convert to unified row shape: source, external_id, subreddit, title, selftext, author, post_url, created_utc."""
    return {
        "source": SOURCE,
        "external_id": submission.id,
        "subreddit": str(submission.subreddit).lower(),
        "title": submission.title or "",
        "selftext": submission.selftext or "",
        "author": getattr(submission, "author", None) and str(submission.author) or "",
        "post_url": getattr(submission, "url", "") or "",
        "created_utc": datetime.fromtimestamp(submission.created_utc, tz=timezone.utc),
    }


def fetch_posts_from_subreddit(subreddit_name: str, limit: int) -> list[dict]:
    """
    Fetch up to `limit` recent posts (capped at PIPELINE_MAX_BATCH) from one subreddit.
    Used for streaming collection: one batch per subreddit, then insert, then release.
    """
    if not reddit_api_credentials_active():
        return []
    limit = clamp_batch_size(limit)
    rows: list[dict] = []
    try:
        reddit = _reddit_client()
        sub = reddit.subreddit(subreddit_name)
        for submission in sub.new(limit=limit):
            if not submission.stickied:
                rows.append(_submission_to_row(submission))
    except Exception as e:
        logger.warning("Failed to fetch from r/%s: %s", subreddit_name, e)
    return rows


def fetch_posts() -> list[dict]:
    """
    Fetch recent public posts from all configured subreddits (requires REDDIT_* env vars).
    Returns list of row dicts; each subreddit contributes at most per_sub_limit (<= PIPELINE_MAX_BATCH).
    """
    if not reddit_api_credentials_active():
        logger.warning(
            "Reddit API disabled (REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET are ``unused``); "
            "use RSS or set real Reddit OAuth credentials."
        )
        return []
    subs = get_subreddit_names_for_ingestion()
    if not subs:
        logger.warning("No subreddits configured for Reddit API ingestion")
        return []
    per_sub = max(1, min(PIPELINE_MAX_BATCH, POSTS_PER_RUN // max(1, len(subs))))
    rows: list[dict] = []
    for sub_name in subs:
        rows.extend(fetch_posts_from_subreddit(sub_name, per_sub))
    logger.info("Reddit API: fetched %d posts from %d subreddits", len(rows), len(subs))
    return rows
