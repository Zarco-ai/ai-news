"""Run ingestion jobs on a schedule."""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from app.db.repository import VideoRepository
from app.db.session import get_session
from app.ingest.youtube_rss import (
    YouTubeVideo,
    discover_recent_videos,
    fetch_transcript,
)

logger = logging.getLogger(__name__)


def run_metadata_ingest(
    *,
    hours: int = 24,
    sources_path: Path | str | None = None,
) -> list[YouTubeVideo]:
    """
    Step 1: scrape RSS metadata and persist videos/channels to the database.
    Transcripts are left as pending for a later batch job.
    """
    videos = discover_recent_videos(hours=hours, sources_path=sources_path)
    if not videos:
        logger.info("No recent videos found in the last %s hours.", hours)
        return []

    with get_session() as session:
        repo = VideoRepository(session)
        created, updated = repo.upsert_videos(videos)

    logger.info(
        "Stored metadata for %d videos (%d created, %d updated).",
        len(videos),
        created,
        updated,
    )
    return videos


def run_transcript_ingest(
    *,
    languages: list[str] | None = None,
    limit: int | None = 50,
    include_failed: bool = True,
) -> int:
    """
    Step 2: fetch transcripts for videos pending in the database.

    Returns the number of transcripts successfully saved.
    """
    success_count = 0

    with get_session() as session:
        repo = VideoRepository(session)
        pending_rows = repo.list_videos_pending_transcript(
            limit=limit,
            include_failed=include_failed,
        )
        pending = [(row.video_id, row.title) for row in pending_rows]

    if not pending:
        logger.info("No videos pending transcript processing.")
        return 0

    logger.info("Processing transcripts for %d videos.", len(pending))

    for video_id, title in pending:
        try:
            transcript = fetch_transcript(video_id, languages=languages)
        except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as exc:
            logger.warning(
                "Transcript unavailable for %s (%s): %s",
                title,
                video_id,
                exc,
            )
            with get_session() as session:
                repo = VideoRepository(session)
                repo.mark_transcript_unavailable(video_id, str(exc))
            continue
        except Exception:
            logger.exception(
                "Transcript fetch failed for %s (%s)",
                title,
                video_id,
            )
            with get_session() as session:
                repo = VideoRepository(session)
                repo.mark_transcript_failed(video_id, "transcript fetch failed")
            continue

        with get_session() as session:
            repo = VideoRepository(session)
            repo.save_transcript(transcript)

        success_count += 1
        logger.info("Saved transcript for %s (%s)", title, video_id)

    logger.info(
        "Transcript batch complete: %d/%d succeeded.",
        success_count,
        len(pending),
    )
    return success_count


def run_scheduled_ingest(
    *,
    job: str,
    interval_hours: int = 24,
    hours_window: int = 24,
    languages: list[str] | None = None,
    sources_path: Path | str | None = None,
    transcript_batch_size: int | None = 50,
    include_failed: bool = True,
    once: bool = False,
) -> None:
    """Run metadata and/or transcript jobs on a fixed interval."""
    interval = timedelta(hours=interval_hours)
    next_run_at: datetime | None = None

    while True:
        started_at = datetime.now(timezone.utc)
        if next_run_at is None:
            next_run_at = started_at + interval

        logger.info("Starting ingest job=%s at %s", job, started_at.isoformat())
        try:
            if job in ("metadata", "both"):
                run_metadata_ingest(hours=hours_window, sources_path=sources_path)
            if job in ("transcripts", "both"):
                run_transcript_ingest(
                    languages=languages,
                    limit=transcript_batch_size,
                    include_failed=include_failed,
                )
        except KeyboardInterrupt:
            raise
        except Exception:
            logger.exception("Ingest job failed (job=%s)", job)
        finally:
            logger.info("Finished ingest job=%s", job)

        if once:
            return

        next_run_at = next_run_at or (started_at + interval)
        now = datetime.now(timezone.utc)
        sleep_seconds = (next_run_at - now).total_seconds()
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        next_run_at = next_run_at + interval


def _parse_languages(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",")]
    return [p for p in parts if p]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Run YouTube RSS ingest (metadata first, transcripts later)"
    )
    parser.add_argument(
        "--job",
        choices=["metadata", "transcripts", "both"],
        default="metadata",
        help=(
            "metadata: RSS scrape + DB storage only; "
            "transcripts: batch transcript fetch for pending videos; "
            "both: run metadata then transcripts."
        ),
    )
    parser.add_argument(
        "--hours-window",
        type=int,
        default=24,
        help="How far back to look for newest videos (metadata job).",
    )
    parser.add_argument(
        "--interval-hours",
        type=int,
        default=24,
        help="How often to run the scheduled job loop.",
    )
    parser.add_argument(
        "--transcript-batch-size",
        type=int,
        default=50,
        help="Max videos to process per transcript batch.",
    )
    parser.add_argument(
        "--no-retry-failed",
        action="store_true",
        help="Only process pending videos; skip previously failed ones.",
    )
    parser.add_argument(
        "--languages",
        type=str,
        default=None,
        help="Comma-separated transcript languages (e.g. 'es,en').",
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

    run_scheduled_ingest(
        job=args.job,
        interval_hours=args.interval_hours,
        hours_window=args.hours_window,
        languages=_parse_languages(args.languages),
        sources_path=args.sources,
        transcript_batch_size=args.transcript_batch_size,
        include_failed=not args.no_retry_failed,
        once=args.once,
    )


"""

This file will turn your current terminal into a console that will renew every 24 hours,
it also works and is able to run data ingestion on youtube channels. 

"""
