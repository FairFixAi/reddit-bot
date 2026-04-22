"""Database layer: ensure schema, insert posts (no username storage)."""
import logging
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import psycopg2
from psycopg2.extras import execute_values

from utils.config import DATABASE_URL, PIPELINE_MAX_BATCH

logger = logging.getLogger(__name__)

_schema_path = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_SQL = _schema_path.read_text() if _schema_path.exists() else ""

_conn_params_logged = False


def _psycopg2_kwargs_from_database_url(url: str) -> dict:
    """Build psycopg2.connect() kwargs from a postgresql:// URI (avoids libpq URI edge cases)."""
    p = urlparse(url)
    if p.scheme not in ("postgres", "postgresql"):
        raise ValueError("DATABASE_URL must start with postgresql:// or postgres://")
    if not p.hostname:
        raise ValueError("DATABASE_URL is missing host")
    dbname = (p.path or "").lstrip("/") or "postgres"
    user = unquote(p.username) if p.username else None
    password = unquote(p.password) if p.password is not None else ""
    kwargs: dict = {
        "host": p.hostname,
        "port": p.port or 5432,
        "dbname": dbname,
        "user": user,
        "password": password,
    }
    if p.query:
        for key, values in parse_qs(p.query, keep_blank_values=True).items():
            if not values:
                continue
            # psycopg2 accepts sslmode, connect_timeout, etc.
            if key in ("sslmode", "connect_timeout", "application_name", "options"):
                kwargs[key] = values[0]
    if "supabase.com" in p.hostname and "sslmode" not in kwargs:
        kwargs["sslmode"] = "require"
    return kwargs


@contextmanager
def get_conn():
    global _conn_params_logged
    kwargs = _psycopg2_kwargs_from_database_url(DATABASE_URL)
    if not _conn_params_logged:
        logger.info(
            "DB connection (from DATABASE_URL): host=%s port=%s user=%s dbname=%s",
            kwargs.get("host"),
            kwargs.get("port"),
            kwargs.get("user"),
            kwargs.get("dbname"),
        )
        pooler = kwargs.get("host", "").endswith(".pooler.supabase.com")
        if pooler and kwargs.get("user") == "postgres":
            logger.warning(
                "Pooler host with user 'postgres' will fail Supabase session auth; "
                "use user postgres.<project-ref> from Connect → Session pooler."
            )
        _conn_params_logged = True
    conn = psycopg2.connect(**kwargs)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema(conn=None) -> None:
    """Create posts table and indexes if they do not exist."""
    if not SCHEMA_SQL.strip():
        logger.warning("schema.sql not found; skipping init_schema")
        return
    parts = [s.strip() for s in SCHEMA_SQL.split(";") if s.strip()]
    statements = []
    for p in parts:
        lines = [ln for ln in p.splitlines() if ln.strip() and not ln.strip().startswith("--")]
        stmt = "\n".join(lines)
        if stmt:
            statements.append(stmt)
    def run(con):
        with con.cursor() as cur:
            for stmt in statements:
                if stmt:
                    cur.execute(stmt)
    if conn is not None:
        run(conn)
        return
    with get_conn() as con:
        run(con)
    logger.info("Schema initialized")


def _rows_to_insert_tuples(rows: list[dict]) -> list[tuple]:
    return [
        (
            r["source"],
            r["external_id"],
            r["subreddit"],
            r["title"],
            r.get("selftext") or "",
            r.get("author"),
            r.get("post_url"),
            r["created_utc"],
        )
        for r in rows
    ]


def _insert_posts_one_chunk(tuples: list[tuple]) -> int:
    """Single commit for one chunk of rows."""
    if not tuples:
        return 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO posts (source, external_id, subreddit, title, selftext, author, post_url, created_utc)
                VALUES %s
                ON CONFLICT (source, external_id) DO NOTHING
                """,
                tuples,
            )
            return cur.rowcount


def insert_posts(rows: list[dict]) -> int:
    """Insert posts. Duplicates (same source + native external_id) are skipped silently via ON CONFLICT DO NOTHING. Chunks commits for peak memory."""
    if not rows:
        return 0
    chunk = max(1, PIPELINE_MAX_BATCH)
    tuples = _rows_to_insert_tuples(rows)
    total_inserted = 0
    n_chunks = (len(tuples) + chunk - 1) // chunk
    for i in range(0, len(tuples), chunk):
        batch = tuples[i : i + chunk]
        total_inserted += _insert_posts_one_chunk(batch)
    if n_chunks > 1:
        logger.info(
            "insert_posts: %d rows in %d chunk(s), chunk_size=%s, inserted ~%d",
            len(tuples),
            n_chunks,
            chunk,
            total_inserted,
        )
    else:
        logger.info("Inserted %d new posts (skipped duplicates)", total_inserted)
    return total_inserted


def get_posts_without_classification(limit: int | None = None) -> list[dict]:
    """Return posts that have no row in post_classifications. If limit is None, returns all unclassified posts (avoid on production workers; use PIPELINE_MAX_BATCH from the caller)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            sql = """
                SELECT p.id, p.title, p.selftext, p.subreddit, p.author, p.post_url, p.created_utc
                FROM posts p
                LEFT JOIN post_classifications c ON c.post_id = p.id
                WHERE c.id IS NULL
                ORDER BY p.id
                """
            if limit is not None:
                sql += " LIMIT %s"
                cur.execute(sql, (limit,))
            else:
                cur.execute(sql)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def insert_classification(
    post_id: int,
    topic: str | None,
    sentiment: str | None,
    emotional_intensity: int | None,
    financial_mention: bool | None,
    financial_amount: str | None,
    problem_category: str | None,
    intent: str | None,
    vehicle_make: str | None,
    vehicle_model: str | None,
    keywords: list[str] | None,
    summary: str | None,
    suggested_action: str | None = None,
) -> None:
    """Insert or replace one classification row for a post."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO post_classifications (
                    post_id, topic, sentiment, emotional_intensity, financial_mention, financial_amount,
                    problem_category, intent, vehicle_make, vehicle_model, keywords, summary, suggested_action
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO UPDATE SET
                    topic = EXCLUDED.topic, sentiment = EXCLUDED.sentiment,
                    emotional_intensity = EXCLUDED.emotional_intensity,
                    financial_mention = EXCLUDED.financial_mention, financial_amount = EXCLUDED.financial_amount,
                    problem_category = EXCLUDED.problem_category, intent = EXCLUDED.intent,
                    vehicle_make = EXCLUDED.vehicle_make, vehicle_model = EXCLUDED.vehicle_model,
                    keywords = EXCLUDED.keywords, summary = EXCLUDED.summary,
                    suggested_action = EXCLUDED.suggested_action,
                    classified_at = NOW()
                """,
                (
                    post_id,
                    topic,
                    sentiment,
                    emotional_intensity,
                    financial_mention,
                    financial_amount,
                    problem_category,
                    intent,
                    vehicle_make,
                    vehicle_model,
                    keywords if keywords else None,
                    summary,
                    suggested_action,
                ),
            )
    logger.info("Stored classification for post_id=%s", post_id)


def delete_posts_older_than_days(days: int) -> int:
    """Delete posts (and their classifications via CASCADE) older than days. Returns count deleted."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM posts WHERE created_utc < NOW() - INTERVAL '1 day' * %s",
                (days,),
            )
            deleted = cur.rowcount
    logger.info("Retention: deleted %d posts older than %s days", deleted, days)
    return deleted


_WEEKLY_REPORT_JOIN_WHERE = """
    FROM posts p
    JOIN post_classifications c ON c.post_id = p.id
    WHERE p.created_utc >= NOW() - INTERVAL '1 day' * %s
       OR c.classified_at >= NOW() - INTERVAL '1 day' * %s
"""


def count_classified_posts_in_report_window(days: int = 7) -> int:
    """Count joined post+classification rows in the weekly report window (same filter as full export)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) AS n {_WEEKLY_REPORT_JOIN_WHERE}",
                (days, days),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0


def get_report_window_counts_by_subreddit(days: int = 7) -> dict[str, int]:
    """GROUP BY subreddit in report window; no post bodies loaded."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(p.subreddit), ''), 'unknown'), COUNT(*)
                {_WEEKLY_REPORT_JOIN_WHERE}
                GROUP BY 1
                """,
                (days, days),
            )
            return {row[0]: row[1] for row in cur.fetchall()}


def get_report_window_counts_by_problem_category(days: int = 7) -> dict[str, int]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(c.problem_category), ''), 'other'), COUNT(*)
                {_WEEKLY_REPORT_JOIN_WHERE}
                GROUP BY 1
                """,
                (days, days),
            )
            return {row[0]: row[1] for row in cur.fetchall()}


def get_report_window_counts_by_intent(days: int = 7) -> dict[str, int]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(NULLIF(TRIM(c.intent), ''), 'unknown'), COUNT(*)
                {_WEEKLY_REPORT_JOIN_WHERE}
                GROUP BY 1
                """,
                (days, days),
            )
            return {row[0]: row[1] for row in cur.fetchall()}


def get_report_window_by_problem_and_vehicle(days: int = 7, limit: int = 150) -> list[dict]:
    """Aggregated problem_category × vehicle_make counts; capped for memory."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(TRIM(c.problem_category), ''), 'other') AS problem_category,
                    COALESCE(NULLIF(TRIM(c.vehicle_make), ''), 'unspecified') AS vehicle_make,
                    COUNT(*) AS count
                {_WEEKLY_REPORT_JOIN_WHERE}
                GROUP BY 1, 2
                ORDER BY count DESC
                LIMIT %s
                """,
                (days, days, limit),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_report_window_suggested_action_counts(days: int = 7) -> dict[str, int]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT LOWER(COALESCE(NULLIF(TRIM(c.suggested_action), ''), 'none')), COUNT(*)
                {_WEEKLY_REPORT_JOIN_WHERE}
                GROUP BY 1
                """,
                (days, days),
            )
            return {row[0]: row[1] for row in cur.fetchall()}


def count_urgent_high_emotional_in_report_window(days: int = 7) -> int:
    """intent = urgent AND emotional_intensity >= 7 within report window."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)
                {_WEEKLY_REPORT_JOIN_WHERE}
                  AND LOWER(TRIM(COALESCE(c.intent, ''))) = 'urgent'
                  AND COALESCE(c.emotional_intensity, 0) >= 7
                """,
                (days, days),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0


def count_financial_mention_in_report_window(days: int = 7) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)
                {_WEEKLY_REPORT_JOIN_WHERE}
                  AND COALESCE(c.financial_mention, FALSE) IS TRUE
                """,
                (days, days),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0


def get_urgent_high_emotional_sample_report_window(days: int = 7, limit: int = 50) -> list[dict]:
    """Recent urgent+high-emotion posts; no selftext."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT p.id, p.title, c.summary, c.emotional_intensity, c.intent, c.classified_at
                {_WEEKLY_REPORT_JOIN_WHERE}
                  AND LOWER(TRIM(COALESCE(c.intent, ''))) = 'urgent'
                  AND COALESCE(c.emotional_intensity, 0) >= 7
                ORDER BY GREATEST(p.created_utc, COALESCE(c.classified_at, p.created_utc)) DESC
                LIMIT %s
                """,
                (days, days, limit),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_financial_mention_sample_report_window(days: int = 7, limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT p.id, p.title, c.summary, c.financial_amount, c.intent, c.classified_at
                {_WEEKLY_REPORT_JOIN_WHERE}
                  AND COALESCE(c.financial_mention, FALSE) IS TRUE
                ORDER BY GREATEST(p.created_utc, COALESCE(c.classified_at, p.created_utc)) DESC
                LIMIT %s
                """,
                (days, days, limit),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _opportunity_score_sql() -> str:
    """Expression matching jobs.weekly_report._opportunity_score (for SQL ORDER BY)."""
    return """
        (
            CASE LOWER(TRIM(COALESCE(c.intent, '')))
                WHEN 'urgent' THEN 40.0
                WHEN 'buying' THEN 35.0
                WHEN 'comparison' THEN 22.0
                WHEN 'research' THEN 18.0
                ELSE 0.0
            END
            + LEAST(COALESCE(c.emotional_intensity, 0), 10) * 3.0
            + CASE WHEN COALESCE(c.financial_mention, FALSE) THEN 25.0 ELSE 0.0 END
            + CASE
                WHEN c.financial_amount IS NOT NULL
                     AND length(trim(c.financial_amount::text)) > 0 THEN 5.0
                ELSE 0.0
              END
            + CASE
                WHEN LOWER(TRIM(COALESCE(c.intent, ''))) = 'urgent'
                     AND COALESCE(c.emotional_intensity, 0) >= 7 THEN 15.0
                ELSE 0.0
              END
            + CASE
                WHEN LOWER(TRIM(COALESCE(c.intent, ''))) = 'buying'
                     AND COALESCE(c.financial_mention, FALSE) THEN 12.0
                ELSE 0.0
              END
        )
    """


def get_top_opportunities_report_window(days: int = 7, limit: int = 10) -> list[dict]:
    """Highest opportunity_score rows; no selftext; capped."""
    score_sql = _opportunity_score_sql()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    p.id,
                    p.title,
                    c.summary,
                    c.problem_category,
                    c.intent,
                    c.suggested_action,
                    c.financial_mention,
                    c.emotional_intensity,
                    ({score_sql.strip()}) AS opportunity_score
                {_WEEKLY_REPORT_JOIN_WHERE}
                ORDER BY ({score_sql.strip()}) DESC, p.id DESC
                LIMIT %s
                """,
                (days, days, limit),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_classified_posts_for_week(days: int = 7) -> list[dict]:
    """Fetch posts + classifications for the report window (includes selftext). For ad-hoc tools only; weekly email uses SQL summaries."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT p.id, p.title, p.selftext, p.subreddit, p.created_utc,
                       c.topic, c.sentiment, c.emotional_intensity, c.financial_mention, c.financial_amount,
                       c.problem_category, c.intent, c.vehicle_make, c.vehicle_model, c.keywords, c.summary,
                       c.classified_at, c.suggested_action
                {_WEEKLY_REPORT_JOIN_WHERE}
                ORDER BY GREATEST(p.created_utc, COALESCE(c.classified_at, p.created_utc)) DESC
                """,
                (days, days),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_problem_category_counts_by_classified_window(
    window_start_days_ago: int, window_end_days_ago: int
) -> dict[str, int]:
    """
    Count rows per problem_category where classified_at is in
    [NOW - window_start_days_ago, NOW - window_end_days_ago), e.g. last 7 days: (7, 0); prior week: (14, 7).
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(NULLIF(TRIM(c.problem_category), ''), 'other'), COUNT(*)
                FROM post_classifications c
                WHERE c.classified_at IS NOT NULL
                  AND c.classified_at >= NOW() - INTERVAL '1 day' * %s
                  AND c.classified_at < NOW() - INTERVAL '1 day' * %s
                GROUP BY 1
                """,
                (window_start_days_ago, window_end_days_ago),
            )
            return {row[0]: row[1] for row in cur.fetchall()}
