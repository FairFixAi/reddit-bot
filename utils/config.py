"""Load configuration from environment variables.

Every variable is required: missing or empty values raise ValueError at import time.
Use RSS_FEED_URLS=DERIVE_FROM_SUBREDDIT_LIST to build feed URLs from SUBREDDIT_LIST.
When USE_RSS=true, set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to the literal ``unused`` (Reddit Data API disabled).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv()


def get_env(key: str) -> str:
    value = os.environ.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"Missing required environment variable: {key}")
    return str(value).strip()


def get_env_default(key: str, default: str) -> str:
    value = os.environ.get(key)
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip()


def get_env_bool(key: str) -> bool:
    v = get_env(key).lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    raise ValueError(f"{key} must be true or false (got {v!r})")


def get_env_bool_default(key: str, default: bool) -> bool:
    v = get_env_default(key, "true" if default else "false").lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    raise ValueError(f"{key} must be true or false (got {v!r})")


def get_env_int(key: str, *, minimum: int | None = 1) -> int:
    raw = get_env(key)
    try:
        n = int(raw, 10)
    except ValueError as e:
        raise ValueError(f"{key} must be an integer (got {raw!r})") from e
    if minimum is not None and n < minimum:
        raise ValueError(f"{key} must be >= {minimum} (got {n})")
    return n


def get_env_int_default(key: str, default: int, *, minimum: int | None = 1) -> int:
    raw = get_env_default(key, str(default))
    try:
        n = int(raw, 10)
    except ValueError as e:
        raise ValueError(f"{key} must be an integer (got {raw!r})") from e
    if minimum is not None and n < minimum:
        raise ValueError(f"{key} must be >= {minimum} (got {n})")
    return n


def get_env_float(key: str, *, minimum: float | None = 0.0) -> float:
    raw = get_env(key)
    try:
        x = float(raw)
    except ValueError as e:
        raise ValueError(f"{key} must be a number (got {raw!r})") from e
    if minimum is not None and x < minimum:
        raise ValueError(f"{key} must be >= {minimum} (got {x})")
    return x


def get_env_float_default(key: str, default: float, *, minimum: float | None = 0.0) -> float:
    raw = get_env_default(key, str(default))
    try:
        x = float(raw)
    except ValueError as e:
        raise ValueError(f"{key} must be a number (got {raw!r})") from e
    if minimum is not None and x < minimum:
        raise ValueError(f"{key} must be >= {minimum} (got {x})")
    return x


RSS_FEED_URLS_DERIVE = "DERIVE_FROM_SUBREDDIT_LIST"
REDDIT_API_DISABLED_MARKER = "unused"
MAX_RECORDS_PER_RUN_HARD_LIMIT = 200


RUN_PIPELINE = get_env_bool_default("RUN_PIPELINE", False)
ALLOW_HISTORICAL_REPROCESSING = get_env_bool_default("ALLOW_HISTORICAL_REPROCESSING", False)
PROCESSING_WINDOW_DAYS = get_env_int_default("PROCESSING_WINDOW_DAYS", 7)

USE_RSS = get_env_bool("USE_RSS")
DATABASE_URL = get_env("DATABASE_URL")

SUBREDDIT_LIST_STR = get_env("SUBREDDIT_LIST")
SUBREDDIT_LIST = [s.strip() for s in SUBREDDIT_LIST_STR.split(",") if s.strip()]
if not SUBREDDIT_LIST:
    raise ValueError("SUBREDDIT_LIST must list at least one subreddit (comma-separated)")

_RSS_FEED_URLS_RAW = get_env("RSS_FEED_URLS")


def get_rss_feeds() -> list[str]:
    if _RSS_FEED_URLS_RAW == RSS_FEED_URLS_DERIVE:
        return [f"https://www.reddit.com/r/{s}/new.rss" for s in SUBREDDIT_LIST]
    urls = [u.strip() for u in _RSS_FEED_URLS_RAW.split(",") if u.strip()]
    if not urls:
        raise ValueError(
            f"RSS_FEED_URLS must be {RSS_FEED_URLS_DERIVE!r} or a comma-separated list of URLs"
        )
    return urls


def get_subreddit_names_for_ingestion() -> list[str]:
    return SUBREDDIT_LIST


FETCH_INTERVAL_MINUTES = get_env_int("FETCH_INTERVAL_MINUTES")
CLASSIFICATION_INTERVAL_MINUTES = get_env_int("CLASSIFICATION_INTERVAL_MINUTES")
RETENTION_DAYS = get_env_int("RETENTION_DAYS")
RETENTION_RUN_INTERVAL_HOURS = get_env_int("RETENTION_RUN_INTERVAL_HOURS")
POSTS_PER_RUN = get_env_int("POSTS_PER_RUN")
PIPELINE_MAX_BATCH = get_env_int("PIPELINE_MAX_BATCH")
RSS_MAX_POSTS_PER_RUN = get_env_int("RSS_MAX_POSTS_PER_RUN")
RSS_DELAY_BETWEEN_FEEDS_SEC = get_env_float("RSS_DELAY_BETWEEN_FEEDS_SEC", minimum=0.0)
CLASSIFICATION_BATCH_SIZE = get_env_int("CLASSIFICATION_BATCH_SIZE")
OPENAI_MAX_RECORDS_PER_RUN = get_env_int_default("OPENAI_MAX_RECORDS_PER_RUN", 150)
OPENAI_RUN_BUDGET_USD = get_env_float_default("OPENAI_RUN_BUDGET_USD", 0.0)
OPENAI_WEEKLY_BUDGET_USD = get_env_float_default("OPENAI_WEEKLY_BUDGET_USD", 0.0)
OPENAI_ESTIMATED_COST_PER_RECORD_USD = get_env_float_default(
    "OPENAI_ESTIMATED_COST_PER_RECORD_USD",
    0.002,
    minimum=0.0,
)
RSS_HTTP_MAX_RETRIES = get_env_int("RSS_HTTP_MAX_RETRIES")
RSS_HTTP_RETRY_BASE_SEC = get_env_float("RSS_HTTP_RETRY_BASE_SEC", minimum=0.01)

REDDIT_CLIENT_ID = get_env("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = get_env("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = get_env("REDDIT_USER_AGENT")
RSS_USER_AGENT = get_env("RSS_USER_AGENT")

OPENAI_API_KEY = get_env_default("OPENAI_API_KEY", "")
REPORT_EMAIL_TO = get_env("REPORT_EMAIL_TO")

SMTP_HOST = get_env("SMTP_HOST")
SMTP_PORT = get_env_int("SMTP_PORT", minimum=1)
SMTP_USER = get_env("SMTP_USER")
SMTP_PASSWORD = get_env("SMTP_PASSWORD")

WEEKLY_REPORT_DAYS = get_env_int("WEEKLY_REPORT_DAYS")
WEEKLY_REPORT_URGENT_SAMPLE_LIMIT = get_env_int("WEEKLY_REPORT_URGENT_SAMPLE_LIMIT")
WEEKLY_REPORT_FINANCIAL_SAMPLE_LIMIT = get_env_int("WEEKLY_REPORT_FINANCIAL_SAMPLE_LIMIT")
WEEKLY_REPORT_PROBLEM_VEHICLE_SQL_LIMIT = get_env_int("WEEKLY_REPORT_PROBLEM_VEHICLE_SQL_LIMIT")


for _key, _value in {
    "POSTS_PER_RUN": POSTS_PER_RUN,
    "PIPELINE_MAX_BATCH": PIPELINE_MAX_BATCH,
    "RSS_MAX_POSTS_PER_RUN": RSS_MAX_POSTS_PER_RUN,
    "CLASSIFICATION_BATCH_SIZE": CLASSIFICATION_BATCH_SIZE,
    "OPENAI_MAX_RECORDS_PER_RUN": OPENAI_MAX_RECORDS_PER_RUN,
}.items():
    if _value > MAX_RECORDS_PER_RUN_HARD_LIMIT:
        raise ValueError(f"{_key} must be <= {MAX_RECORDS_PER_RUN_HARD_LIMIT} (got {_value})")


def clamp_batch_size(n: int) -> int:
    return max(1, min(PIPELINE_MAX_BATCH, n))


def effective_classification_batch_size() -> int:
    return max(1, min(CLASSIFICATION_BATCH_SIZE, OPENAI_MAX_RECORDS_PER_RUN))


def reddit_api_credentials_active() -> bool:
    """False when Reddit Data API is intentionally disabled (RSS-only)."""
    m = REDDIT_API_DISABLED_MARKER.lower()
    return REDDIT_CLIENT_ID.lower() != m and REDDIT_CLIENT_SECRET.lower() != m
