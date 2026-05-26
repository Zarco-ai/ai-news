"""Run ingestion jobs."""

from app.ingest.youtube_rss import run_daily_check


def run_youtube_ingest(*, hours: int = 24, fetch_transcripts: bool = True):
    """Discover recent YouTube videos and optionally fetch transcripts."""
    return run_daily_check(hours=hours, fetch_transcripts=fetch_transcripts)
