"""
Test script: build weekly report and send email to test recipient only (babsgodwin@gmail.com).
Production (main.py) uses REPORT_EMAIL_TO from .env; this script never uses production recipient.
"""
import json
import logging
import sys

from jobs.weekly_report import build_json_summary, build_email_body, build_email_html, send_report_email
from utils.pipeline_control import ensure_pipeline_enabled

# Test-only recipient; production uses REPORT_EMAIL_TO from .env
TEST_REPORT_EMAIL = "babsgodwin@gmail.com"
#TEST_REPORT_EMAIL = "alan@modernenginepros.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main() -> None:
    ensure_pipeline_enabled()
    logger.info("Building weekly summary (test)...")
    summary = build_json_summary()
    json_str = json.dumps(summary, indent=2)
    body = build_email_body(summary)
    html_body = build_email_html(summary)
    logger.info("Sending test report to %s (not production recipient)", TEST_REPORT_EMAIL)
    if send_report_email(body, json_str, TEST_REPORT_EMAIL, html_body=html_body):
        logger.info("Test weekly report sent to %s", TEST_REPORT_EMAIL)
    else:
        logger.error("Failed to send test report")
        sys.exit(1)


if __name__ == "__main__":
    main()
