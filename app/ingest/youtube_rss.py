"""Fetch recent YouTube videos via channel RSS and optional transcripts."""

from __future__ import annotations # Allows for the use of Python features in modules containing the future statement before statement is standard 

import logging # Logging is a module that provides a logger object that can be used to log messages to a file or console.
from dataclasses import dataclass, field    # Provides decorators and functions for automatically adding generated special methods.
                                            # dataclass is a decorator that automatically adds generated special methods to a class.
from datetime import datetime, timedelta, timezone # upplies classes for parsing, manipulating and calculating differences in timedelta, and standardizing timezones for dates and times.                                 
from pathlib import Path # OOP approach to handling filesystem paths, allows for cross-platform compatibility.
from typing import Any # Allows for static type hinting, 'Any' indicates to type checkers a variable or parameter has an unconstrained type.

import feedparser # Provides a way to parse RSS feeds.
import requests # Provides a way to ma ke HTTP requests.
import yaml # Provides a way to read and write YAML files, mapping configuration blocks safely into python.
from youtube_transcript_api import YouTubeTranscriptApi # Provides a way to fetch transcripts for YouTube videos.
from youtube_transcript_api._errors import (
    NoTranscriptFound, # Raised when a transcript is not found for a video.
    TranscriptsDisabled, # Raised when a transcript is disabled for a video.
    VideoUnavailable, # Raised when a video is unavailable.
)

logger = logging.getLogger(__name__) # Gets the logger for the current module.

YOUTUBE_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}" # RSS feed URL for a YouTube channel.
DEFAULT_SOURCES_PATH = Path(__file__).resolve().parents[2] / "data" / "sources.yaml" # Default path to the sources.yaml file.
                                                                                     # Path(__file__).resolve() gets the absolute path of the current script.
                                                                                     # .parents[2] goes up two levels from the current script to the project root.
                                                                                     # / "data" / "sources.yaml" is the path to the sources.yaml file.
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; ai-news-bot/1.0)" # Default user agent for the requests library.
                                                                 # This sets a custom header string that identifies your script to web servers when making HTTP requests, preventing it from being blocked as an anonymous or default bot.


'''
Below the decorator '@dataclass' tells python to autogenerate boilerplate methods for a class, such as __init__, __repr__, __eq__, __hash__, etc.
Inside each class, the class attributes are defined with type hints.
the 'frozen=True' argument tells python to make the class immutable, meaning that the attributes cannot be changed after the object is created.
'''


@dataclass(frozen=True)
class YouTubeChannel:
    channel_id: str
    label: str = ""


@dataclass(frozen=True)
class YouTubeVideo:
    video_id: str
    title: str
    url: str
    published_at: datetime
    channel_id: str
    channel_label: str = ""
    description: str = ""


@dataclass
class VideoWithTranscript:
    video: YouTubeVideo
    transcript_text: str
    transcript_language: str | None = None # Allows for the transcript language to be None, indicating that the transcript is not available in another language.


def load_channels(sources_path: Path | str | None = None) -> list[YouTubeChannel]: # Type hints say argument may be a Path, string or None, while returning a list of the YouTubeChannel class. 
    """Load channel list from data/sources.yaml."""
    path = Path(sources_path) if sources_path else DEFAULT_SOURCES_PATH # If sources_path is provided, use it, otherwise use the default path.
    with path.open(encoding="utf-8") as f: # Opens the file in utf-8 encoding. 'bytes' is the default encoding for files.
        data = yaml.safe_load(f) or {} # Loads the data from the file into a dictionary. 'safe_load' is a method that loads the data from the file into a dictionary, and 'or' is a logical operator that returns the first truthy value.

    channels: list[YouTubeChannel] = [] # Initializes an empty list of YouTubeChannel objects.
    for entry in data.get("youtube_channels", []):
        channel_id = entry.get("channel_id", "").strip()
        if not channel_id:
            continue
        channels.append(
            YouTubeChannel( # Creates a new YouTubeChannel object with the channel_id and label within the 'channels' list. This gets done for each entry in the data dictionary.
                channel_id=channel_id,
                label=entry.get("label", "") or channel_id, 
            )
        )
    return channels


def build_rss_url(channel_id: str) -> str: # Type hints say argument is a string, while returning a string.
    """
    YouTube exposes an Atom RSS feed per channel.

    Required input: channel_id (UC…), NOT the @handle.
    """
    return YOUTUBE_RSS_URL.format(channel_id=channel_id)


def _parse_published(value: str) -> datetime:
    """Parse Atom published timestamp to UTC-aware datetime."""
    if hasattr(value, "tm_year"):
        return datetime(*value[:6], tzinfo=timezone.utc)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fetch_channel_videos(
    channel: YouTubeChannel,
    *,
    session: requests.Session | None = None,
    max_entries: int | None = 15,
) -> list[YouTubeVideo]: # Type hints say argument is a YouTubeChannel object, while returning a list of the YouTubeVideo class. session may be a requests.Session object or None, max_entries may be an integer or None.

    """Fetch latest videos from a channel's RSS feed."""
    url = build_rss_url(channel.channel_id)
    http = session or requests.Session() # If session is provided, use it, otherwise create a new requests.Session object.
                                         # a 'session' is a request.Session object that persist certain parameters across http requests.
    http.headers.setdefault("User-Agent", DEFAULT_USER_AGENT) # Sets the User-Agent header to the default user agent.
                                                            # setdefault is a method that sets a default value for a key if the key is not already in the dictionary.

    response = http.get(url, timeout=30)
    response.raise_for_status() # Raises an exception if the response status code is not 200.

    feed = feedparser.parse(response.content) # Parses the response content into a feedparser object.
    if feed.bozo and not feed.entries:
        raise ValueError(
            f"Failed to parse RSS for {channel.label} ({channel.channel_id}): {feed.bozo_exception}"
        )

    videos: list[YouTubeVideo] = [] # Initializes an empty list of YouTubeVideo objects.
    for entry in feed.entries[:max_entries] if max_entries else feed.entries: # If max_entries is provided, use it, otherwise use all the entries.
        video_id = entry.get("yt_videoid") or _video_id_from_entry(entry)
        if not video_id:
            logger.warning("Skipping entry without video id: %s", entry.get("title"))
            continue

        published = _parse_published(entry.get("published_parsed") or entry.get("published", "")) # Parses the published date from the entry, and turnsit into UTC time
        link = entry.get("link") or f"https://www.youtube.com/watch?v={video_id}"

        videos.append(
            YouTubeVideo(
                video_id=video_id,
                title=entry.get("title", "").strip(),
                url=link,
                published_at=published,
                channel_id=channel.channel_id,
                channel_label=channel.label,
                description=entry.get("summary", "").strip(),
            )
        )

    return videos


def _video_id_from_entry(entry: dict[str, Any]) -> str | None: # Type hints say argument is a dictionary with string keys and any values, while returning a string or None.
    """Extract video id from Atom link if yt_videoid is missing."""
    link = entry.get("link", "")
    if "v=" in link:
        return link.split("v=")[-1].split("&")[0]
    return None


def filter_videos_since(
    videos: list[YouTubeVideo],
    since: datetime | timedelta,
) -> list[YouTubeVideo]: # Type hints say argument is a list of YouTubeVideo objects, and a datetime or timedelta, while returning a list of the YouTubeVideo class.

    """Keep only videos published at or after `since`."""
    if isinstance(since, timedelta): # If since is a timedelta, convert it to a datetime object.
                                     # 'isinstance' is a built-in function that checks if an object is an instance of a class.
        since = datetime.now(timezone.utc) - since

    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    since = since.astimezone(timezone.utc)

    return [v for v in videos if v.published_at >= since]


def discover_recent_videos(
    channels: list[YouTubeChannel] | None = None,
    *,
    hours: int = 24,
    sources_path: Path | str | None = None,
    session: requests.Session | None = None,
) -> list[YouTubeVideo]:
    """
    Check all configured channels for videos published in the last `hours`.

    Typical daily cron usage: discover_recent_videos(hours=24)
    """
    channels = channels or load_channels(sources_path)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    recent: list[YouTubeVideo] = []

    http = session or requests.Session()
    for channel in channels:
        try:
            videos = fetch_channel_videos(channel, session=http)
            channel_recent = filter_videos_since(videos, since)
            logger.info(                        # Logs a message to the console. '%s' is a placeholder for the channel label, '%d' is a placeholder for the number of recent videos, '%d' is a placeholder for the number of fetched videos (all found in the next few lines).
                "%s: %d recent / %d fetched",
                channel.label,
                len(channel_recent),
                len(videos),
            )
            recent.extend(channel_recent)
        except requests.HTTPError as exc:
            logger.error(
                "RSS HTTP error for %s (%s): %s",
                channel.label,
                channel.channel_id,
                exc,
            )
        except Exception as exc:
            logger.error(
                "Failed to fetch %s (%s): %s",
                channel.label,
                channel.channel_id,
                exc,
            )

    recent.sort(key=lambda v: v.published_at, reverse=True) # Sorts the recent list of YouTubeVideo objects by published date in descending order.
    return recent


def fetch_transcript(
    video_id: str,
    *,
    languages: list[str] | None = None,
) -> tuple[str, str | None]: # Type hints say argument is a string, while returning a tuple of a string and a string or None.

    """
    Fetch transcript text for a video using youtube-transcript-api.

    Returns (full_text, language_code).
    Raises on missing/disabled transcripts.
    """
    
    languages = languages or ["es", "en"]
    api = YouTubeTranscriptApi()
    fetched = api.fetch(video_id, languages=languages)

    snippets = fetched.to_raw_data()
    language = getattr(fetched, "language", None) or (
        snippets[0].get("language") if snippets else None
    )
    text = " ".join(s["text"].strip() for s in snippets if s.get("text"))
    return text, language


def fetch_transcript_safe(
    video_id: str,
    *,
    languages: list[str] | None = None,
) -> VideoWithTranscript | None:

    """Like fetch_transcript but returns None instead of raising."""
    try:
        text, language = fetch_transcript(video_id, languages=languages)
        return VideoWithTranscript(
            video=YouTubeVideo(
                video_id=video_id,
                title="",
                url=f"https://www.youtube.com/watch?v={video_id}",
                published_at=datetime.now(timezone.utc),
                channel_id="",
            ),
            transcript_text=text,
            transcript_language=language,
        )
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as exc:
        logger.warning("No transcript for %s: %s", video_id, exc)
        return None


def enrich_with_transcripts(
    videos: list[YouTubeVideo],
    *,
    languages: list[str] | None = None,
) -> list[VideoWithTranscript]:

    """Attach transcripts to videos; skip videos where transcript is unavailable."""
    results: list[VideoWithTranscript] = []
    for video in videos:
        try:
            text, language = fetch_transcript(video.video_id, languages=languages)
            results.append(
                VideoWithTranscript(
                    video=video,
                    transcript_text=text,
                    transcript_language=language,
                )
            )
        except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable) as exc:
            logger.warning(
                "Skipping %s (%s): %s",
                video.title,
                video.video_id,
                exc,
            )
    return results


def run_daily_check(
    *,
    hours: int = 24,
    fetch_transcripts: bool = True,
    languages: list[str] | None = None,
    sources_path: Path | str | None = None,
) -> list[VideoWithTranscript] | list[YouTubeVideo]:

    """
    End-to-end: discover recent videos, optionally fetch transcripts.

    Returns videos (with or without transcript payloads).
    """
    recent = discover_recent_videos(hours=hours, sources_path=sources_path)
    if not fetch_transcripts:
        return recent
    return enrich_with_transcripts(recent, languages=languages)


def _print_results(items: list[YouTubeVideo] | list[VideoWithTranscript]) -> None:
    if not items:
        print("No recent videos found in the configured time window.")
        return

    for item in items:
        if isinstance(item, VideoWithTranscript):
            video = item.video
            extra = f"\n  transcript ({item.transcript_language}): {item.transcript_text[:200]}..."
        else:
            video = item
            extra = ""
        print(
            f"- [{video.channel_label}] {video.title}\n"
            f"  id: {video.video_id}\n"
            f"  published: {video.published_at.isoformat()}\n"
            f"  url: {video.url}{extra}"
        )


if __name__ == "__main__":

    """
    The code beneath 'if __name__ == "__main__":' Is meant to first log this script run to our console.
    It also is meant to get the parameters needed to run the functions above, which it does, and then
    it runs the full script.
    """

    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Test YouTube RSS + transcript ingest") 
    parser.add_argument(
        "--hours",
        type=int,
        default=24 * 7,
        help="Look back window in hours (default: 7 days for easier testing)",
    )
    parser.add_argument(
        "--no-transcript",
        action="store_true",
        help="Skip transcript fetching",
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=None,
        help="Path to sources.yaml",
    )
    args = parser.parse_args()

    
    results = run_daily_check(
        hours=args.hours,
        fetch_transcripts=not args.no_transcript,
        sources_path=args.sources,
    )

    _print_results(results)


