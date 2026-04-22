"""
Run ingestion: fetch from Reddit RSS (default) or Reddit API, then store in DB.
Used by main.py each cron tick. Standalone: ``python -m jobs.run_collection`` runs one cycle and exits.
"""
import logging
import time

from utils.config import (
    USE_RSS,
    PIPELINE_MAX_BATCH,
    RSS_DELAY_BETWEEN_FEEDS_SEC,
    RSS_MAX_POSTS_PER_RUN,
    get_rss_feeds,
    get_subreddit_names_for_ingestion,
)
from data.db import insert_posts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def _run_rss_once_chunked() -> int:
    """
    One feed at a time: fetch small list, insert to Supabase, drop references before next feed.
    Avoids holding all feeds' posts in one Python list (Render OOM mitigation).
    """
    from data.rss_fetcher import fetch_posts_from_single_feed

    total_inserted = 0
    remaining = max(1, RSS_MAX_POSTS_PER_RUN)
    feeds = get_rss_feeds()
    delay = max(0.0, RSS_DELAY_BETWEEN_FEEDS_SEC)
    for i, url in enumerate(feeds):
        if remaining <= 0:
            logger.info("RSS: global cap %s reached; skipping further feeds", RSS_MAX_POSTS_PER_RUN)
            break
        if i > 0 and delay > 0:
            time.sleep(delay)
        rows = fetch_posts_from_single_feed(url, max_entries=remaining)
        if rows:
            n_new = 0
            for j in range(0, len(rows), PIPELINE_MAX_BATCH):
                chunk = rows[j : j + PIPELINE_MAX_BATCH]
                n_new += insert_posts(chunk)
            total_inserted += n_new
            remaining -= len(rows)
            logger.info(
                "RSS: processed %d row(s) from feed, %d new in DB, %d budget left this cycle",
                len(rows),
                n_new,
                remaining,
            )
    return total_inserted


def run_once() -> int:
    """One fetch cycle. Returns number of new posts inserted."""
    if USE_RSS:
        return _run_rss_once_chunked()
    from data.reddit_client import fetch_posts_from_subreddit

    total_inserted = 0
    subs = get_subreddit_names_for_ingestion()
    for sub in subs:
        batch = fetch_posts_from_subreddit(sub, PIPELINE_MAX_BATCH)
        if not batch:
            continue
        for j in range(0, len(batch), PIPELINE_MAX_BATCH):
            chunk = batch[j : j + PIPELINE_MAX_BATCH]
            total_inserted += insert_posts(chunk)
    return total_inserted


def main() -> None:
    """One collection cycle then exit (for cron or manual runs)."""
    try:
        n = run_once()
        logger.info("Collection: %d new posts stored", n)
    except Exception as e:
        logger.exception("Collection failed: %s", e)


if __name__ == "__main__":
    main()
