"""
OpenAI-based classification for Reddit posts.
Output: topic, sentiment, emotional_intensity, financial_mention, financial_amount,
        problem_category, intent, vehicle_make, vehicle_model, keywords, summary.
Null for any field when not clearly available (no guessing).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from utils.config import OPENAI_API_KEY
from utils.pipeline_control import ensure_pipeline_enabled

logger = logging.getLogger(__name__)

# Fixed predefined categories (per scope)
TOPIC_CHOICES = ["Automotive Repair", "General Question", "Comparison", "Other"]
SENTIMENT_CHOICES = ["positive", "neutral", "negative"]
INTENT_CHOICES = ["urgent", "research", "comparison", "buying"]
PROBLEM_CATEGORIES = ["engine", "transmission", "brakes", "overheating", "electrical", "suspension", "other"]
SUGGESTED_ACTION_CHOICES = ["google_ads", "landing_page", "reddit_reply", "blog_content", "none"]

SYSTEM_PROMPT = """You classify automotive/repair Reddit posts. Reply with a single JSON object only. Use null only when the field cannot be inferred at all.

Fields:
- topic: one of """ + str(TOPIC_CHOICES) + """
- sentiment: one of """ + str(SENTIMENT_CHOICES) + """
- emotional_intensity: integer 1-10 (1=calm, 10=very stressed)
- financial_mention: true only if money/cost is clearly mentioned
- financial_amount: extracted amount as string if present, else null
- problem_category: one of """ + str(PROBLEM_CATEGORIES) + """. Do NOT use null if you have keywords or a summary that indicate an automotive issue — infer the best-matching category. Use "other" only when none of the listed categories fit.
- intent: one of """ + str(INTENT_CHOICES) + """ — use "buying" for shopping/which-car-to-buy/decision posts; "urgent" for time-sensitive repair; "research" for learning/diagnosis; "comparison" for comparing options.
- suggested_action: one of """ + str(SUGGESTED_ACTION_CHOICES) + """ — pick the single best marketing follow-up: google_ads (high purchase/repair intent + money or urgent commercial signal); landing_page (category or comparison landing page fits); reddit_reply (good thread for expert engagement); blog_content (evergreen how-to/educational SEO); none (low signal).
- vehicle_make: only if clearly stated (e.g. Honda, Toyota), else null
- vehicle_model: only if clearly stated, else null
- keywords: array of 4-8 SHORT problem-level terms (symptoms/parts/issues), NOT generic words. Good: engine knocking, misfire, overheating, brake squeal, transmission slip, check engine, coolant leak. Bad: car, repair, help, question, advice, mechanic, problem (unless paired with a symptom). Prefer concrete automotive terms from the post.
- summary: 1-2 clean sentences summarizing the issue, else null

Maximize classification coverage: when keywords or summary describe a problem, always set problem_category. Keep output consistent and concise."""


def classify_post(title: str, selftext: str, subreddit: str) -> dict[str, Any]:
    """Classify one post. Returns dict with keys matching post_classifications. Uses null when not available."""
    ensure_pipeline_enabled()
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=OPENAI_API_KEY, max_retries=0)
    user_content = f"Subreddit: r/{subreddit}\nTitle: {title}\n\nBody:\n{selftext[:4000] if selftext else '(no body)'}"
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=600,
    )
    text = resp.choices[0].message.content
    # Strip markdown code block if present
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    data = json.loads(text.strip())
    # Normalize types
    out = {
        "topic": data.get("topic"),
        "sentiment": data.get("sentiment"),
        "emotional_intensity": _int_or_none(data.get("emotional_intensity")),
        "financial_mention": _bool_or_none(data.get("financial_mention")),
        "financial_amount": _str_or_none(data.get("financial_amount")),
        "problem_category": _str_or_none(data.get("problem_category")),
        "intent": _normalize_intent(data.get("intent")),
        "suggested_action": _normalize_suggested_action(data.get("suggested_action")),
        "vehicle_make": _str_or_none(data.get("vehicle_make")),
        "vehicle_model": _str_or_none(data.get("vehicle_model")),
        "keywords": _keywords_list(data.get("keywords")),
        "summary": _str_or_none(data.get("summary")),
    }
    return out


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _bool_or_none(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("true", "1", "yes")


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _keywords_list(v: Any) -> list[str] | None:
    if v is None:
        return None
    if isinstance(v, list):
        words = [str(x).strip() for x in v if str(x).strip()][:8]
        return words if words else None
    return None


def _normalize_intent(v: Any) -> str | None:
    s = _str_or_none(v)
    if not s:
        return None
    s = s.lower().strip()
    if s in INTENT_CHOICES:
        return s
    return None


def _normalize_suggested_action(v: Any) -> str | None:
    s = _str_or_none(v)
    if not s:
        return "none"
    s = s.lower().strip().replace(" ", "_").replace("-", "_")
    aliases = {
        "googlead": "google_ads",
        "google_ads": "google_ads",
        "ads": "google_ads",
        "landing": "landing_page",
        "landingpage": "landing_page",
        "reddit": "reddit_reply",
        "reply": "reddit_reply",
        "blog": "blog_content",
        "content": "blog_content",
        "seo": "blog_content",
        "none": "none",
    }
    s = aliases.get(s, s)
    if s in SUGGESTED_ACTION_CHOICES:
        return s
    return "none"
