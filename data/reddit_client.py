"""Reddit API client: auth and fetch public posts (optional when using RSS)."""
import logging
from datetime import datetime, timezone

import praw
from praw.models import Submission

from utils.config import (
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_USER_AGENT,
    SUBREDDIT_LIST,
    POSTS_PER_RUN,
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


def fetch_posts() -> list[dict]:
    """
    Fetch recent public posts from configured subreddits (requires REDDIT_* env vars).
    Returns list of row dicts in unified shape for insert_posts.
    """
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET or not REDDIT_USER_AGENT:
        logger.warning("Reddit API credentials not set; use RSS (USE_RSS=true) or set REDDIT_* env vars.")
        return []
    if not SUBREDDIT_LIST:
        logger.warning("SUBREDDIT_LIST is empty")
        return []
    reddit = _reddit_client()
    limit_per_sub = max(10, POSTS_PER_RUN // max(1, len(SUBREDDIT_LIST)))
    rows: list[dict] = []
    for sub_name in SUBREDDIT_LIST:
        try:
            sub = reddit.subreddit(sub_name)
            for submission in sub.new(limit=limit_per_sub):
                if not submission.stickied:
                    rows.append(_submission_to_row(submission))
        except Exception as e:
            logger.warning("Failed to fetch from r/%s: %s", sub_name, e)
    logger.info("Reddit API: fetched %d posts from %d subreddits", len(rows), len(SUBREDDIT_LIST))
    return rows
