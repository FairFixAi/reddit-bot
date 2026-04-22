"""
Reddit Bot – single entrypoint for production.
Run once on the server; handles collection, classification, retention, and weekly report on schedule.

On Render **Web Service**, `PORT` is set: a tiny HTTP server binds for health checks while the
scheduler runs in a background thread. Locally, omit `PORT` to run the scheduler only (no HTTP).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import date, datetime, timezone

from utils.config import (
    FETCH_INTERVAL_MINUTES,
    CLASSIFICATION_INTERVAL_MINUTES,
    RETENTION_RUN_INTERVAL_HOURS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Intervals in seconds
COLLECTION_INTERVAL = FETCH_INTERVAL_MINUTES * 60
CLASSIFICATION_INTERVAL = CLASSIFICATION_INTERVAL_MINUTES * 60
RETENTION_INTERVAL = RETENTION_RUN_INTERVAL_HOURS * 60 * 60

# Last run timestamps (0 = run soon)
_last_collection = 0.0
_last_classification = 0.0
_last_retention = 0.0
# Weekly report: only on Monday (UTC); last date we sent so we send at most once per Monday
_last_weekly_report_date: date | None = None


class _HealthHandler(BaseHTTPRequestHandler):
    """Minimal handler so Render Web Service sees an open port."""

    def log_message(self, format: str, *args) -> None:
        pass  # avoid noisy per-request logs on health checks

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"ok\n")


def _run_collection() -> None:
    from jobs.run_collection import run_once

    try:
        n = run_once()
        logger.info("Collection: %d new posts stored", n)
    except Exception as e:
        logger.exception("Collection failed: %s", e)


def _run_classification() -> None:
    try:
        from jobs.run_classification import main as classification_main

        classification_main()
    except Exception as e:
        logger.exception("Classification failed: %s", e)


def _run_retention() -> None:
    try:
        from jobs.run_retention import main as retention_main

        retention_main()
    except Exception as e:
        logger.exception("Retention failed: %s", e)


def _run_weekly_report() -> None:
    try:
        from jobs.weekly_report import main as report_main

        report_main()
    except Exception as e:
        logger.exception("Weekly report failed: %s", e)


def scheduler_loop() -> None:
    global _last_collection, _last_classification, _last_retention, _last_weekly_report_date
    logger.info(
        "Reddit Bot scheduler started. Collection every %s min, classification every %s min, "
        "retention per RETENTION_RUN_INTERVAL_HOURS, weekly report on Mondays (UTC) only.",
        FETCH_INTERVAL_MINUTES,
        CLASSIFICATION_INTERVAL_MINUTES,
    )
    while True:
        now = time.time()
        if now - _last_collection >= COLLECTION_INTERVAL:
            _run_collection()
            _last_collection = now
        if now - _last_classification >= CLASSIFICATION_INTERVAL:
            _run_classification()
            _last_classification = now
        if now - _last_retention >= RETENTION_INTERVAL:
            _run_retention()
            _last_retention = now
        today_utc = datetime.now(timezone.utc).date()
        if today_utc.weekday() == 0 and _last_weekly_report_date != today_utc:
            _run_weekly_report()
            _last_weekly_report_date = today_utc
        time.sleep(60)


def _run_health_server(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    logger.info("Listening on 0.0.0.0:%s for health checks", port)
    server.serve_forever()


def main() -> None:
    port_raw = os.environ.get("PORT")
    if port_raw:
        port = int(port_raw)
        worker = threading.Thread(
            target=scheduler_loop,
            name="reddit-bot-scheduler",
            daemon=True,
        )
        worker.start()
        _run_health_server(port)
    else:
        scheduler_loop()


if __name__ == "__main__":
    main()
