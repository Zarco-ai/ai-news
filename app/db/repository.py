"""CRUD repository for YouTube ingest tables."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Channel, Transcript, TranscriptStatus, Video
from app.ingest.youtube_rss import YouTubeTranscript, YouTubeVideo


class VideoRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_channel(self, channel_id: str, label: str = "") -> Channel:
        channel = self.session.get(Channel, channel_id)
        if channel is None:
            channel = Channel(channel_id=channel_id, label=label)
            self.session.add(channel)
        elif label and channel.label != label:
            channel.label = label
        return channel

    def upsert_video(self, video: YouTubeVideo) -> tuple[Video, bool]:
        """
        Insert or update video metadata.

        Returns (row, created) where created is True for a new row.
        """
        self.upsert_channel(video.channel_id, video.channel_label)

        row = self.session.get(Video, video.video_id)
        created = row is None
        if row is None:
            row = Video(
                video_id=video.video_id,
                channel_id=video.channel_id,
                title=video.title,
                url=video.url,
                description=video.description,
                published_at=video.published_at,
                transcript_status=TranscriptStatus.PENDING,
            )
            self.session.add(row)
        else:
            row.title = video.title
            row.url = video.url
            row.description = video.description
            row.published_at = video.published_at
            if row.channel_id != video.channel_id:
                row.channel_id = video.channel_id

        return row, created

    def upsert_videos(self, videos: list[YouTubeVideo]) -> tuple[int, int]:
        """Upsert many videos. Returns (created_count, updated_count)."""
        created_count = 0
        updated_count = 0
        for video in videos:
            _, created = self.upsert_video(video)
            if created:
                created_count += 1
            else:
                updated_count += 1
        self.session.flush()
        return created_count, updated_count

    def list_videos_pending_transcript(
        self,
        *,
        limit: int | None = 50,
        include_failed: bool = True,
    ) -> list[Video]:
        statuses = [TranscriptStatus.PENDING]
        if include_failed:
            statuses.append(TranscriptStatus.FAILED)

        stmt = (
            select(Video)
            .where(Video.transcript_status.in_(statuses))
            .order_by(Video.published_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

    def save_transcript(self, transcript: YouTubeTranscript) -> Transcript:
        video = self.session.get(Video, transcript.video_id)
        if video is None:
            raise ValueError(f"Video {transcript.video_id} not found in database")

        row = self.session.get(Transcript, transcript.video_id)
        if row is None:
            row = Transcript(
                video_id=transcript.video_id,
                text=transcript.text,
                language=transcript.language,
                fetched_at=datetime.now(timezone.utc),
            )
            self.session.add(row)
        else:
            row.text = transcript.text
            row.language = transcript.language
            row.fetched_at = datetime.now(timezone.utc)

        video.transcript_status = TranscriptStatus.SUCCESS
        video.transcript_error = None
        return row

    def mark_transcript_unavailable(self, video_id: str, error: str) -> None:
        video = self.session.get(Video, video_id)
        if video is None:
            return
        video.transcript_status = TranscriptStatus.UNAVAILABLE
        video.transcript_error = error[:2000]

    def mark_transcript_failed(self, video_id: str, error: str) -> None:
        video = self.session.get(Video, video_id)
        if video is None:
            return
        video.transcript_status = TranscriptStatus.FAILED
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