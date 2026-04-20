"""
Run ingestion: fetch from Reddit RSS (default) or Reddit API, then store in DB.
Used by main.py on a schedule. Can also be run standalone (loops every FETCH_INTERVAL_MINUTES).
"""
import logging
import time

from utils.config import (
    USE_RSS,
    FETCH_INTERVAL_MINUTES,
    RSS_DELAY_BETWEEN_FEEDS_SEC,
    RSS_MAX_POSTS_PER_RUN,
    get_rss_feeds,
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
            n_new = insert_posts(rows)
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
    from data.reddit_client import fetch_posts

    rows = fetch_posts()
    return insert_posts(rows)


def main() -> None:
    logger.info("Collection loop: every %s minutes", FETCH_INTERVAL_MINUTES)
    while True:
        try:
            n = run_once()
            logger.info("Collection: %d new posts stored", n)
        except Exception as e:
            logger.exception("Collection failed: %s", e)
        time.sleep(FETCH_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
