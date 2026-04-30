"""Fetch public posts from Reddit RSS feeds (no API credentials required)."""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone

import feedparser
import requests

from utils.config import RSS_HTTP_MAX_RETRIES, RSS_HTTP_RETRY_BASE_SEC, RSS_USER_AGENT

logger = logging.getLogger(__name__)

SOURCE = "reddit_rss"


def _subreddit_from_feed_url(url: str) -> str:
    """Extract subreddit name from feed URL, e.g. .../r/MechanicAdvice/new.rss -> mechanicadvice."""
    m = re.search(r"/r/([^/]+)/", url, re.I)
    return m.group(1).lower() if m else "unknown"


def _parse_date(entry) -> datetime | None:
    """Parse entry published/updated into timezone-aware datetime (feedparser uses UTC)."""
    for key in ("published_parsed", "updated_parsed"):
        t = getattr(entry, key, None)
        if t and isinstance(t, time.struct_time) and len(t) >= 6:
            return datetime(t[0], t[1], t[2], t[3], t[4], t[5], tzinfo=timezone.utc)
    return None


def _entry_to_row(entry, subreddit: str) -> dict:
    """Map RSS entry to row. Full body text as returned by the feed — no truncation at storage."""
    link = getattr(entry, "link", "") or ""
    title = getattr(entry, "title", "") or ""
    selftext = ""
    if getattr(entry, "content", None):
        selftext = entry.content[0].get("value") or ""
    if not selftext and getattr(entry, "description", None):
        selftext = entry.description or ""
    author = getattr(entry, "author", "") or ""
    if not author and hasattr(entry, "dc_creator"):
        author = entry.dc_creator or ""
    published = _parse_date(entry) or datetime.now(timezone.utc)
    return {
        "source": SOURCE,
        "external_id": link or getattr(entry, "id", ""),
        "subreddit": subreddit,
        "title": title,
        "selftext": selftext,
        "author": author,
        "post_url": link,
        "created_utc": published,
    }


def _http_get_feed(url: str) -> requests.Response | None:
    """
    GET with retries. Reddit often returns 429 for datacenter IPs when requests are too close together;
    honors Retry-After and exponential backoff.
    """
    headers = {"User-Agent": RSS_USER_AGENT}
    # Strict batch mode: one HTTP attempt only. Keep the env var for deployment compatibility,
    # but do not perform automatic retry loops.
    max_retries = min(RSS_HTTP_MAX_RETRIES, 1)
    base = RSS_HTTP_RETRY_BASE_SEC
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=45, headers=headers)
            if resp.status_code == 429:
                wait = base * (2**attempt)
                ra = resp.headers.get("Retry-After")
                if ra is not None:
                    try:
                        wait = max(wait, float(ra))
                    except ValueError:
                        pass
                if attempt >= max_retries - 1:
                    logger.warning(
                        "RSS 429 rate limited (no more retries): %s — set a unique RSS_USER_AGENT or reduce feeds",
                        url,
                    )
                    return None
                logger.warning(
                    "RSS 429 for %s, sleeping %.1fs then retry %s/%s",
                    url,
                    wait,
                    attempt + 2,
                    max_retries,
                )
                time.sleep(wait)
                continue
            if 500 <= resp.status_code < 600:
                if attempt >= max_retries - 1:
                    resp.raise_for_status()
                wait = base * (2**attempt)
                logger.warning("RSS %s for %s, sleeping %.1fs", resp.status_code, url, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_exc = e
            if attempt >= max_retries - 1:
                break
            wait = base * (2**attempt)
            logger.warning("RSS request error for %s: %s; retry in %.1fs", url, e, wait)
            time.sleep(wait)
    if last_exc:
        logger.warning("Failed to fetch RSS %s after retries: %s", url, last_exc)
    return None


def fetch_posts_from_single_feed(feed_url: str, max_entries: int) -> list[dict]:
    """
    Fetch up to max_entries from one RSS URL. Returns a small list (no cross-feed accumulation).
    HTTP body and parsed feed are released when this returns.
    """
    rows: list[dict] = []
    cap = max(1, max_entries)
    resp = _http_get_feed(feed_url)
    if resp is None:
        return rows
    try:
        doc = feedparser.parse(resp.content)
        subreddit = _subreddit_from_feed_url(feed_url)
        for entry in doc.entries:
            if len(rows) >= cap:
                break
            try:
                row = _entry_to_row(entry, subreddit)
                if row["external_id"]:
                    rows.append(row)
            except Exception as e:
                logger.debug("Skip entry %s: %s", getattr(entry, "link", ""), e)
    except Exception as e:
        logger.warning("Failed to parse RSS %s: %s", feed_url, e)
    return rows


def fetch_posts_from_rss() -> list[dict]:
    """
    Fetch from all configured feeds into one list (tests / diagnostics only).
    Production uses jobs.run_collection per-feed fetch + insert to avoid one giant in-memory list.
    """
    from utils.config import RSS_DELAY_BETWEEN_FEEDS_SEC, get_rss_feeds, RSS_MAX_POSTS_PER_RUN

    feeds = get_rss_feeds()
    out: list[dict] = []
    remaining = max(1, RSS_MAX_POSTS_PER_RUN)
    delay = max(0.0, RSS_DELAY_BETWEEN_FEEDS_SEC)
    for i, url in enumerate(feeds):
        if remaining <= 0:
            break
        if i > 0 and delay > 0:
            time.sleep(delay)
        batch = fetch_posts_from_single_feed(url, max_entries=remaining)
        out.extend(batch)
        remaining -= len(batch)
    logger.info("RSS: fetched %d posts from %d feeds (cap=%s)", len(out), len(feeds), RSS_MAX_POSTS_PER_RUN)
    return out
