"""Load configuration from environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from reddit-bot project root (parent of utils)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def get_env(key: str, default: str | None = None) -> str:
    value = os.environ.get(key, default)
    if value is None or value == "":
        raise ValueError(f"Missing required environment variable: {key}")
    return value


def get_env_optional(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key, default)
    return value if value else default


# Use RSS (no Reddit API credentials). When True, REDDIT_* are optional.
USE_RSS = get_env_optional("USE_RSS", "true").lower() in ("1", "true", "yes")

# Database (required)
DATABASE_URL = get_env("DATABASE_URL")

# RSS feeds (used when USE_RSS=true): comma-separated URLs
RSS_FEED_URLS_RAW = get_env_optional("RSS_FEED_URLS") or ""
RSS_FEED_URLS = [u.strip() for u in RSS_FEED_URLS_RAW.split(",") if u.strip()]

# If no RSS_FEED_URLS, build from subreddit list (same as before)
SUBREDDIT_LIST = [s.strip() for s in (get_env_optional("SUBREDDIT_LIST") or "").split(",") if s.strip()]

# Default RSS feeds when none provided (client examples)
DEFAULT_RSS_FEEDS = [
    "https://www.reddit.com/r/MechanicAdvice/new.rss",
    "https://www.reddit.com/r/Cartalk/new.rss",
    "https://www.reddit.com/r/AskMechanics/new.rss",
    "https://www.reddit.com/r/AutoRepair/new.rss",
    "https://www.reddit.com/r/UsedCars/new.rss",
]

def get_rss_feeds() -> list[str]:
    if RSS_FEED_URLS:
        return RSS_FEED_URLS
    if SUBREDDIT_LIST:
        return [f"https://www.reddit.com/r/{s}/new.rss" for s in SUBREDDIT_LIST]
    return DEFAULT_RSS_FEEDS

# Fetch interval in minutes (collection runs every N minutes)
FETCH_INTERVAL_MINUTES = int(get_env_optional("FETCH_INTERVAL_MINUTES") or "5")
# Classification runs every N minutes (main.py)
CLASSIFICATION_INTERVAL_MINUTES = int(get_env_optional("CLASSIFICATION_INTERVAL_MINUTES") or "60")
# Max posts to classify per run (avoids loading unbounded rows / long OpenAI runs; ~25 safer on 512MB Render)
CLASSIFICATION_BATCH_SIZE = int(get_env_optional("CLASSIFICATION_BATCH_SIZE") or "25")

# Weekly report: attach full post list to JSON (large memory); default off for Render stability
WEEKLY_REPORT_INCLUDE_FULL_POSTS = get_env_optional("WEEKLY_REPORT_INCLUDE_FULL_POSTS", "false").lower() in (
    "1",
    "true",
    "yes",
)

# Reddit API (optional when USE_RSS=true)
REDDIT_CLIENT_ID = get_env_optional("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = get_env_optional("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = get_env_optional("REDDIT_USER_AGENT")

# Optional
POSTS_PER_RUN = int(get_env_optional("POSTS_PER_RUN") or "100")

# RSS collection (USE_RSS=true): cap rows per cycle and max body chars per entry (memory on Render)
RSS_MAX_POSTS_PER_RUN = int(get_env_optional("RSS_MAX_POSTS_PER_RUN") or str(POSTS_PER_RUN))
RSS_MAX_SELFTEXT_CHARS = int(get_env_optional("RSS_MAX_SELFTEXT_CHARS") or "50000")

# DB insert: commit each chunk (smaller peak RAM than one giant execute_values)
INSERT_POSTS_CHUNK_SIZE = int(get_env_optional("INSERT_POSTS_CHUNK_SIZE") or "25")

# Classification: optional max selftext length sent to the model (unset = no truncation)
_cm = get_env_optional("CLASSIFICATION_MAX_SELFTEXT_CHARS", "")
CLASSIFICATION_MAX_SELFTEXT_CHARS = int(_cm) if _cm.strip() else None

# Milestone 2: OpenAI classification
OPENAI_API_KEY = get_env_optional("OPENAI_API_KEY")

# Milestone 2: Weekly report email recipient (all reports go here)
REPORT_EMAIL_TO = get_env_optional("REPORT_EMAIL_TO") or "alan@modernenginepros.com"

# Milestone 2: 90-day rolling retention
RETENTION_DAYS = int(get_env_optional("RETENTION_DAYS") or "90")

# Milestone 2: SMTP for weekly report
SMTP_HOST = get_env_optional("SMTP_HOST") or "smtp.gmail.com"
SMTP_PORT = int(get_env_optional("SMTP_PORT") or "587")
SMTP_USER = get_env_optional("SMTP_USER")
SMTP_PASSWORD = get_env_optional("SMTP_PASSWORD")
