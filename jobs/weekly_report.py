"""
Generate weekly JSON summary and send formatted email report to REPORT_EMAIL_TO.
Uses same SMTP pattern as test_smtp.py. Sends both plain-text and HTML (template).

Aggregates and capped slices are loaded via SQL (no full post bodies) so the job
stays memory-safe on small hosts (e.g. Render). Full post export in JSON is disabled.
"""
import json
import logging
import smtplib
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from utils.config import (
    REPORT_EMAIL_TO,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    WEEKLY_REPORT_DAYS,
    WEEKLY_REPORT_FINANCIAL_SAMPLE_LIMIT,
    WEEKLY_REPORT_PROBLEM_VEHICLE_SQL_LIMIT,
    WEEKLY_REPORT_URGENT_SAMPLE_LIMIT,
)
from data.db import (
    count_classified_posts_in_report_window,
    count_financial_mention_in_report_window,
    count_urgent_high_emotional_in_report_window,
    get_financial_mention_sample_report_window,
    get_problem_category_counts_by_classified_window,
    get_report_window_by_problem_and_vehicle,
    get_report_window_counts_by_intent,
    get_report_window_counts_by_problem_category,
    get_report_window_counts_by_subreddit,
    get_report_window_suggested_action_counts,
    get_top_opportunities_report_window,
    get_urgent_high_emotional_sample_report_window,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _serialize_row(row: dict) -> dict:
    """Convert row for JSON (datetime, list)."""
    out = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, list):
            out[k] = v
        else:
            out[k] = v
    return out


def _opportunity_score(r: dict) -> float:
    """Rank posts for business priority (urgency, buying intent, emotion, money)."""
    score = 0.0
    intent = (r.get("intent") or "").lower()
    if intent == "urgent":
        score += 40.0
    elif intent == "buying":
        score += 35.0
    elif intent == "comparison":
        score += 22.0
    elif intent == "research":
        score += 18.0
    ei = int(r.get("emotional_intensity") or 0)
    score += min(ei, 10) * 3.0
    if r.get("financial_mention"):
        score += 25.0
    if r.get("financial_amount"):
        score += 5.0
    if intent == "urgent" and ei >= 7:
        score += 15.0
    if intent == "buying" and r.get("financial_mention"):
        score += 12.0
    return score


def _cluster_trends() -> list[dict]:
    """Rising / stable / declining by problem cluster vs prior week (by classified_at)."""
    try:
        d = WEEKLY_REPORT_DAYS
        current = get_problem_category_counts_by_classified_window(d, 0)
        prior = get_problem_category_counts_by_classified_window(d * 2, d)
    except Exception as e:
        logger.warning("Cluster trends query failed (classified_at or DB): %s", e)
        return []
    all_cats = set(current) | set(prior)
    out = []
    for cat in sorted(all_cats):
        c = current.get(cat, 0)
        p = prior.get(cat, 0)
        if p == 0 and c == 0:
            continue
        if p == 0 and c > 0:
            trend = "rising"
        elif c > p * 1.25:
            trend = "rising"
        elif p > 0 and c < p * 0.75:
            trend = "declining"
        else:
            trend = "stable"
        out.append(
            {
                "cluster": cat,
                "count_this_week_classified": c,
                "count_prior_week_classified": p,
                "trend": trend,
            }
        )
    out.sort(key=lambda x: -x["count_this_week_classified"])
    return out


def _snippet_from_row(r: dict, max_len: int = 80) -> str:
    s = (r.get("summary") or r.get("title") or "").strip()
    return (s[:max_len] + "…") if len(s) > max_len else s


def _insights_from_db(days: int) -> dict:
    """Insights from SQL aggregates and capped reads (no full-window post list in memory)."""
    by_cat = get_report_window_counts_by_problem_category(days)
    most_common_issues = sorted(by_cat.items(), key=lambda x: -x[1])[:5]

    urgent_sample = get_urgent_high_emotional_sample_report_window(
        days, limit=WEEKLY_REPORT_URGENT_SAMPLE_LIMIT
    )
    financial_sample = get_financial_mention_sample_report_window(
        days, limit=WEEKLY_REPORT_FINANCIAL_SAMPLE_LIMIT
    )
    top_rows = get_top_opportunities_report_window(days, limit=10)

    most_urgent_problems = [_snippet_from_row(r) for r in urgent_sample[:10]]
    potential_high_value = [
        {
            "snippet": _snippet_from_row(r),
            "amount": r.get("financial_amount"),
            "intent": r.get("intent"),
        }
        for r in financial_sample[:10]
    ]

    top_10_opportunities = []
    for i, r in enumerate(top_rows, start=1):
        score_val = r.get("opportunity_score")
        try:
            score_f = float(score_val) if score_val is not None else _opportunity_score(r)
        except (TypeError, ValueError):
            score_f = _opportunity_score(r)
        top_10_opportunities.append(
            {
                "rank": i,
                "score": round(score_f, 1),
                "snippet": _snippet_from_row(r, 100),
                "cluster": r.get("problem_category") or "other",
                "intent": r.get("intent"),
                "suggested_action": r.get("suggested_action") or "none",
                "financial_mention": bool(r.get("financial_mention")),
                "emotional_intensity": r.get("emotional_intensity"),
            }
        )

    by_pv = get_report_window_by_problem_and_vehicle(days, limit=WEEKLY_REPORT_PROBLEM_VEHICLE_SQL_LIMIT)

    return {
        "urgent_high_emotional_sample": [_serialize_row(r) for r in urgent_sample],
        "urgent_high_emotional_count": count_urgent_high_emotional_in_report_window(days),
        "financial_mention_sample": [_serialize_row(r) for r in financial_sample],
        "financial_mention_count": count_financial_mention_in_report_window(days),
        "by_problem_and_vehicle": by_pv,
        "cluster_trends": _cluster_trends(),
        "suggested_action_breakdown": get_report_window_suggested_action_counts(days),
        "top_opportunities": {
            "most_urgent_problems": most_urgent_problems,
            "most_common_issues": [{"problem_category": c, "count": n} for c, n in most_common_issues],
            "potential_high_value_cases": potential_high_value,
            "top_10_ranked": top_10_opportunities,
        },
    }


def build_json_summary() -> dict:
    """Build weekly summary for JSON export (compact by default; no full post bodies)."""
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period_days": WEEKLY_REPORT_DAYS,
        "total_posts": count_classified_posts_in_report_window(WEEKLY_REPORT_DAYS),
        "by_subreddit": get_report_window_counts_by_subreddit(WEEKLY_REPORT_DAYS),
        "by_problem_category": get_report_window_counts_by_problem_category(WEEKLY_REPORT_DAYS),
        "by_intent": get_report_window_counts_by_intent(WEEKLY_REPORT_DAYS),
    }
    summary["insights"] = _insights_from_db(WEEKLY_REPORT_DAYS)
    summary["notes"] = {
        "trend_basis": (
            f"Cluster trends compare counts of classifications by problem_category where classified_at "
            f"fell in this week vs the prior week ({WEEKLY_REPORT_DAYS}-day windows)."
        ),
        "top_10_basis": "Top 10 ranked by internal opportunity score (urgency, buying intent, emotion, financial mention).",
        "data_scope": "Summary and capped samples only (no full post list in JSON).",
    }
    return summary


def build_email_body(summary: dict) -> str:
    """Plain-text formatted report for email."""
    lines = [
        "Reddit Bot – Weekly Report",
        "=" * 40,
        f"Generated: {summary['generated_at']}",
        f"Total classified posts: {summary['total_posts']}",
        "",
        "By subreddit:",
    ]
    for sub, count in sorted(summary["by_subreddit"].items(), key=lambda x: -x[1]):
        lines.append(f"  r/{sub}: {count}")
    lines.extend(["", "By problem category:"])
    for cat, count in sorted(summary["by_problem_category"].items(), key=lambda x: -x[1]):
        lines.append(f"  {cat}: {count}")
    lines.extend(["", "By intent:"])
    for intent, count in sorted(summary["by_intent"].items(), key=lambda x: -x[1]):
        lines.append(f"  {intent}: {count}")

    ins = summary.get("insights") or {}
    lines.extend(["", "--- Highlights ---", ""])
    lines.append(f"Urgent + high emotional (intent=urgent, intensity 7+): {ins.get('urgent_high_emotional_count', 0)} posts")
    lines.append(f"Posts with financial mention: {ins.get('financial_mention_count', 0)}")
    lines.extend(["", "By problem + vehicle (top):"])
    for pv in (ins.get("by_problem_and_vehicle") or [])[:10]:
        lines.append(f"  {pv.get('problem_category', '')} / {pv.get('vehicle_make', '')}: {pv.get('count', 0)}")

    top = ins.get("top_opportunities") or {}
    lines.extend(["", "--- Top 10 opportunities (ranked) ---", ""])
    for item in (top.get("top_10_ranked") or [])[:10]:
        lines.append(
            f"  #{item.get('rank', 0)} score={item.get('score', 0)} | {item.get('cluster', '')} | "
            f"intent={item.get('intent', '')} | action={item.get('suggested_action', '')} | {item.get('snippet', '')}"
        )

    lines.extend(["", "--- Cluster trends (by classification date vs prior week) ---", ""])
    for ct in (ins.get("cluster_trends") or [])[:10]:
        lines.append(
            f"  {ct.get('cluster', '')}: {ct.get('trend', '')} "
            f"(this week {ct.get('count_this_week_classified', 0)}, prior {ct.get('count_prior_week_classified', 0)})"
        )

    lines.extend(["", "--- Suggested actions (this report window) ---", ""])
    for action, cnt in sorted((ins.get("suggested_action_breakdown") or {}).items(), key=lambda x: -x[1]):
        lines.append(f"  {action}: {cnt}")

    lines.extend(["", "--- Top opportunities (summary) ---", ""])
    lines.append("Most urgent problems:")
    for s in (top.get("most_urgent_problems") or [])[:5]:
        lines.append(f"  · {s}")
    lines.append("Most common issues (clusters):")
    for x in (top.get("most_common_issues") or [])[:5]:
        lines.append(f"  · {x.get('problem_category', '')}: {x.get('count', 0)}")
    lines.append("Potential high-value (financial mention):")
    for x in (top.get("potential_high_value_cases") or [])[:5]:
        amt = x.get("amount") or ""
        lines.append(f"  · {x.get('snippet', '')}" + (f" (${amt})" if amt else ""))

    lines.extend(["", "Full JSON is attached to this email.", ""])
    return "\n".join(lines)


def build_email_html(summary: dict) -> str:
    """Load HTML template and fill placeholders with summary data."""
    template_path = Path(__file__).resolve().parent.parent / "templates" / "email_template.html"
    if not template_path.exists():
        logger.warning("HTML template not found at %s; using plain text only", template_path)
        return ""
    html = template_path.read_text(encoding="utf-8")
    # Format generated_at for human-readable display (e.g. March 18, 2025 at 7:00 PM UTC)
    gen = summary.get("generated_at", "")
    if gen:
        try:
            s = gen.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            gen = dt.strftime("%B %d, %Y at %I:%M %p UTC").replace(" at 0", " at ")  # e.g. March 18, 2025 at 7:00 PM UTC
        except (ValueError, TypeError):
            pass
    by_sub = "".join(
        f'<tr><td style="padding: 10px 14px; font-size: 14px; color: #334155;">r/{sub}</td>'
        f'<td style="padding: 10px 14px; font-size: 14px; color: #334155; text-align: right;">{count}</td></tr>'
        for sub, count in sorted(summary["by_subreddit"].items(), key=lambda x: -x[1])
    )
    by_cat = "".join(
        f'<tr><td style="padding: 10px 14px; font-size: 14px; color: #334155;">{cat}</td>'
        f'<td style="padding: 10px 14px; font-size: 14px; color: #334155; text-align: right;">{count}</td></tr>'
        for cat, count in sorted(summary["by_problem_category"].items(), key=lambda x: -x[1])
    )
    by_intent = "".join(
        f'<tr><td style="padding: 10px 14px; font-size: 14px; color: #334155;">{intent}</td>'
        f'<td style="padding: 10px 14px; font-size: 14px; color: #334155; text-align: right;">{count}</td></tr>'
        for intent, count in sorted(summary["by_intent"].items(), key=lambda x: -x[1])
    )
    ins = summary.get("insights") or {}
    by_pv = "".join(
        f'<tr><td style="padding: 8px 12px; font-size: 13px; color: #334155;">{pv.get("problem_category", "")}</td>'
        f'<td style="padding: 8px 12px; font-size: 13px; color: #334155;">{pv.get("vehicle_make", "")}</td>'
        f'<td style="padding: 8px 12px; font-size: 13px; color: #334155; text-align: right;">{pv.get("count", 0)}</td></tr>'
        for pv in (ins.get("by_problem_and_vehicle") or [])[:12]
    )
    top = ins.get("top_opportunities") or {}
    def _esc(s: str) -> str:
        return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def _action_label(a: str) -> str:
        return {
            "google_ads": "Google Ads",
            "landing_page": "Landing page",
            "reddit_reply": "Reddit reply",
            "blog_content": "Blog content",
            "none": "None",
        }.get((a or "none").lower(), a or "none")

    top_10_rows = "".join(
        f'<tr>'
        f'<td style="padding: 8px 10px; font-size: 12px; color: #334155; font-weight: 600;">{item.get("rank", "")}</td>'
        f'<td style="padding: 8px 10px; font-size: 12px; color: #334155;">{_esc(str(item.get("score", "")))}</td>'
        f'<td style="padding: 8px 10px; font-size: 12px; color: #334155;">{_esc(item.get("snippet", ""))}</td>'
        f'<td style="padding: 8px 10px; font-size: 12px; color: #334155;">{_esc(item.get("cluster", ""))}</td>'
        f'<td style="padding: 8px 10px; font-size: 12px; color: #334155;">{_esc(str(item.get("intent", "")))}</td>'
        f'<td style="padding: 8px 10px; font-size: 12px; color: #334155;">{_esc(_action_label(item.get("suggested_action", "")))}</td>'
        f'</tr>'
        for item in (top.get("top_10_ranked") or [])[:10]
    )

    trend_style = {"rising": "#059669", "declining": "#dc2626", "stable": "#64748b"}
    cluster_trend_rows = "".join(
        f'<tr>'
        f'<td style="padding: 8px 10px; font-size: 12px; color: #334155;">{_esc(ct.get("cluster", ""))}</td>'
        f'<td style="padding: 8px 10px; font-size: 12px; font-weight: 600; color: {trend_style.get(ct.get("trend", ""), "#64748b")};">{_esc(ct.get("trend", ""))}</td>'
        f'<td style="padding: 8px 10px; font-size: 12px; color: #334155; text-align: right;">{ct.get("count_this_week_classified", 0)}</td>'
        f'<td style="padding: 8px 10px; font-size: 12px; color: #334155; text-align: right;">{ct.get("count_prior_week_classified", 0)}</td>'
        f'</tr>'
        for ct in (ins.get("cluster_trends") or [])[:12]
    )

    suggested_action_lines = "".join(
        f'<p style="margin: 4px 0; font-size: 13px; color: #334155;"><strong>{_action_label(action)}</strong>: {cnt}</p>'
        for action, cnt in sorted((ins.get("suggested_action_breakdown") or {}).items(), key=lambda x: -x[1])
    )

    top_urgent = "".join(f'<li style="margin: 4px 0; font-size: 13px; color: #334155;">{_esc(s)}</li>' for s in (top.get("most_urgent_problems") or [])[:5])
    top_common = "".join(f'<li style="margin: 4px 0; font-size: 13px; color: #334155;">{c}: {n}</li>' for c, n in [(x.get("problem_category"), x.get("count")) for x in (top.get("most_common_issues") or [])[:5]])
    top_value = "".join(
        f'<li style="margin: 4px 0; font-size: 13px; color: #334155;">{_esc(x.get("snippet", ""))}'
        + (f' <span style="color: #059669;">({x.get("amount", "")})</span>' if x.get("amount") else "") + '</li>'
        for x in (top.get("potential_high_value_cases") or [])[:5]
    )
    html = html.replace("{{generated_at}}", gen)
    html = html.replace("{{total_posts}}", str(summary.get("total_posts", 0)))
    html = html.replace("{{urgent_high_emotional_count}}", str(ins.get("urgent_high_emotional_count", 0)))
    html = html.replace("{{financial_mention_count}}", str(ins.get("financial_mention_count", 0)))
    html = html.replace("{{by_subreddit_rows}}", by_sub or "<tr><td colspan=\"2\" style=\"padding: 10px 14px; color: #64748b;\">No data</td></tr>")
    html = html.replace("{{by_problem_category_rows}}", by_cat or "<tr><td colspan=\"2\" style=\"padding: 10px 14px; color: #64748b;\">No data</td></tr>")
    html = html.replace("{{by_intent_rows}}", by_intent or "<tr><td colspan=\"2\" style=\"padding: 10px 14px; color: #64748b;\">No data</td></tr>")
    html = html.replace("{{by_problem_vehicle_rows}}", by_pv or "<tr><td colspan=\"3\" style=\"padding: 10px 14px; color: #64748b;\">No data</td></tr>")
    html = html.replace("{{top_opportunities_urgent}}", top_urgent or "<li style=\"color: #64748b;\">None this week</li>")
    html = html.replace("{{top_opportunities_common}}", top_common or "<li style=\"color: #64748b;\">None</li>")
    html = html.replace("{{top_opportunities_high_value}}", top_value or "<li style=\"color: #64748b;\">None this week</li>")
    html = html.replace(
        "{{top_10_opportunities_rows}}",
        top_10_rows or "<tr><td colspan=\"6\" style=\"padding: 10px; color: #64748b;\">No data</td></tr>",
    )
    html = html.replace(
        "{{cluster_trend_rows}}",
        cluster_trend_rows or "<tr><td colspan=\"4\" style=\"padding: 10px; color: #64748b;\">No trend data yet</td></tr>",
    )
    html = html.replace(
        "{{suggested_action_summary}}",
        suggested_action_lines or "<p style=\"color: #64748b;\">No breakdown</p>",
    )
    return html


def send_report_email(body: str, json_str: str, to_email: str, html_body: str = "") -> bool:
    """Send report via SMTP. Attaches plain text, optional HTML, and JSON file."""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.error("SMTP_USER and SMTP_PASSWORD required in .env")
        return False
    msg = MIMEMultipart("mixed")
    msg["From"] = SMTP_USER
    msg["To"] = to_email
    msg["Subject"] = f"Reddit Bot – Weekly Report ({datetime.now(timezone.utc).strftime('%Y-%m-%d')})"
    if html_body:
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body, "plain"))
        alt.attach(MIMEText(html_body, "html"))
        msg.attach(alt)
    else:
        msg.attach(MIMEText(body, "plain"))
    part = MIMEBase("application", "json")
    part.set_payload(json_str.encode("utf-8"))
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename="weekly_summary.json")
    msg.attach(part)
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
        return True
    except Exception as e:
        logger.exception("SMTP failed: %s", e)
        return False


def main() -> None:
    logger.info("Building weekly summary (last %s days)...", WEEKLY_REPORT_DAYS)
    t0 = time.perf_counter()
    summary = build_json_summary()
    build_s = time.perf_counter() - t0
    json_str = json.dumps(summary, indent=2)
    json_bytes = len(json_str.encode("utf-8"))
    logger.info(
        "Weekly summary: build %.2fs, JSON %d bytes, total_posts=%s",
        build_s,
        json_bytes,
        summary.get("total_posts"),
    )
    body = build_email_body(summary)
    html_body = build_email_html(summary)
    to_email = REPORT_EMAIL_TO or "alan@modernenginepros.com"
    logger.info("Sending report to %s", to_email)
    if send_report_email(body, json_str, to_email, html_body=html_body):
        logger.info("Weekly report sent")
    else:
        logger.error("Weekly report email failed. Fix SMTP/REPORT_EMAIL_TO and check logs.")
    # Optionally write JSON to file for inspection
    out_path = "weekly_summary.json"
    with open(out_path, "w") as f:
        f.write(json_str)
    logger.info("Wrote %s", out_path)


if __name__ == "__main__":
    main()
