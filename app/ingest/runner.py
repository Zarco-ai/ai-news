"""Run ingestion jobs on a schedule."""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.ingest.youtube_rss import _print_results, run_daily_check

logger = logging.getLogger(__name__)


def run_youtube_ingest(
    *,                      # the ' * ' is a function signature marker meaning when you call the function you must specify the keywords in the arguments
    hours: int = 24,
    fetch_transcripts: bool = True,
    languages: list[str] | None = None,
    sources_path: Path | str | None = None,
):
    """Discover recent YouTube videos and optionally fetch transcripts."""
    return run_daily_check(
        hours=hours,
        fetch_transcripts=fetch_transcripts,
        languages=languages,
        sources_path=sources_path,
    )


def run_youtube_ingest_forever(
    *,
    interval_hours: int = 24,
    hours_window: int = 24,
    fetch_transcripts: bool = True,
    languages: list[str] | None = None,
    sources_path: Path | str | None = None,
    once: bool = False,
) -> None:
    """
    Run the YouTube RSS scrape on a fixed interval.

    `hours_window` controls the look-back window for "newest videos".
    """

    interval = timedelta(hours=interval_hours)
    next_run_at: datetime | None = None

    while True:
        started_at = datetime.now(timezone.utc)
        if next_run_at is None:
            next_run_at = started_at + interval

        logger.info("Starting YouTube ingest at %s", started_at.isoformat())
        try:
            results = run_youtube_ingest(
                hours=hours_window,
                fetch_transcripts=fetch_transcripts,
                languages=languages,
                sources_path=sources_path,
            )
            _print_results(results)
        except KeyboardInterrupt:
            raise
        except Exception:
            logger.exception("YouTube ingest failed")
        finally:
            logger.info("Finished YouTube ingest")

        if once:
            return

        # Sleep until the computed next run time (drift-resistant).
        next_run_at = next_run_at or (started_at + interval)
        now = datetime.now(timezone.utc)
        sleep_seconds = (next_run_at - now).total_seconds()
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

        # Schedule subsequent runs.
        next_run_at = next_run_at + interval


def _parse_languages(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Run YouTube RSS ingest every 24 hours")
    parser.add_argument(
        "--hours-window",
        type=int,
        default=24,
        help="How far back to look for newest videos (default: 24).",
    )
    parser.add_argument(
        "--interval-hours",
        type=int,
        default=24,
        help="How often to run the scraper (default: 24).",
    )
    parser.add_argument(
        "--no-transcript",
        action="store_true",
        help="Skip transcript fetching.",
    )
    parser.add_argument(
        "--languages",
        type=str,
        default=None,
        help="Comma-separated transcript languages (e.g. 'es,en'). If omitted, defaults to youtube_rss.py.",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=None,
        help="Path to sources.yaml",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run once and exit (useful for testing).",
    )
    args = parser.parse_args()

    run_youtube_ingest_forever(
        interval_hours=args.interval_hours,
        hours_window=args.hours_window,
        fetch_transcripts=not args.no_transcript,
        languages=_parse_languages(args.languages),
        sources_path=args.sources,
        once=args.once,
    )
