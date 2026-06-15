"""CRUD repository for YouTube ingest tables."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Channel, Transcript, Video
from app.ingest.youtube_rss import YouTubeTranscript, YouTubeVideo


class VideoRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_channel(self, channel_id: str, label: str = "") -> Channel:
        channel = self.session.get(Channel, channel_id)
        if channel is None:
            channel = Channel(channel_id=channel_id, label=label)
            self.session.add(channel)
            self.session.flush()
        elif label and channel.label != label:
            channel.label = label
        return channel

    def insert_video(self, video: YouTubeVideo) -> tuple[Video, bool]:
        """
        Insert video metadata when the video_id is new.

        Returns (row, created). Existing rows are returned unchanged (skipped).
        """
        self.upsert_channel(video.channel_id, video.channel_label)

        row = self.session.get(Video, video.video_id)
        if row is not None:
            return row, False

        row = Video(
            video_id=video.video_id,
            channel_id=video.channel_id,
            title=video.title,
            url=video.url,
            description=video.description,
            published_at=video.published_at,
        )
        self.session.add(row)
        return row, True

    def insert_videos(self, videos: list[YouTubeVideo]) -> tuple[int, int]:
        """Insert new videos only. Returns (created_count, skipped_count)."""
        created_count = 0
        skipped_count = 0
        for video in videos:
            _, created = self.insert_video(video)
            if created:
                created_count += 1
            else:
                skipped_count += 1
        self.session.flush()
        return created_count, skipped_count

    def list_videos_needing_transcript(
        self,
        *,
        limit: int | None = 50,
        include_failed: bool = True,
    ) -> list[Video]:
        """Videos with no transcript row yet (optionally excluding prior failures)."""
        stmt = (
            select(Video)
            .outerjoin(Transcript, Video.video_id == Transcript.video_id)
            .where(Transcript.video_id.is_(None))
        )
        if not include_failed:
            stmt = stmt.where(Video.transcript_error.is_(None))

        stmt = stmt.order_by(Video.published_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

    def save_transcript(self, transcript: YouTubeTranscript) -> Transcript | None:
        video = self.session.get(Video, transcript.video_id)
        if video is None:
            raise ValueError(f"Video {transcript.video_id} not found in database")

        row = self.session.get(Transcript, transcript.video_id)
        if row is not None:
            return row

        row = Transcript(
            video_id=transcript.video_id,
            text=transcript.text,
            language=transcript.language,
            fetched_at=datetime.now(timezone.utc),
        )
        self.session.add(row)
        video.transcript_error = None
        return row

    def record_transcript_failure(self, video_id: str, error: str) -> None:
        video = self.session.get(Video, video_id)
        if video is None:
            return
        if self.session.get(Transcript, video_id) is not None:
            return
        video.transcript_error = error[:2000]

    def get_video(self, video_id: str) -> Video | None:
        return self.session.get(Video, video_id)

    def list_recent_videos(self, *, limit: int = 20) -> list[Video]:
        stmt = select(Video).order_by(Video.published_at.desc()).limit(limit)
        return list(self.session.scalars(stmt))


"""

All this file is is an API for the file "runner.py" to use because in "runner.py" 
it uses data ingestion tools from "youtube_rss.py", as well as ORM (from SQLAlchemy) from "repository.py"
which makes us capable of putting our data into our relational Database (SQL). 

"""
