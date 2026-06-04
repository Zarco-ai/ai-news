"""SQLAlchemy models for YouTube ingest."""

from __future__ import annotations # postpones evaluation of type annotations

from datetime import datetime # Supplies standard type for manipulating dates and times in Python
from enum import StrEnum # Creates enumeration constants that are also subclasses of strings

from sqlalchemy import DateTime, ForeignKey, String, Text, func # DateTime: SQL-agnostic type that maps python 'datetime' objects to time columns
                                                                # ForeignKey: Defines a dependency constraint indicating that a column value must exist in a column of another table.
                                                                # String: variable-length string SQL type
                                                                # Text: Represents an unbounded or large variable-length string SQL type
                                                                # func: An generator object used to invoke SQL functions (like NOW(), COUNT(), or MAX()) natively in queries.

from sqlalchemy.orm import Mapped, mapped_column, relationship  # Mapped: A generic type configuration wrapper used in modern declarative mapping to denote a class attribute as a database coloumn
                                                                # mapped_coloumn: The primary ORM construct used to customize column behavior (like nullability, defaults, or keys) inside a Mapped type declaration.
                                                                # relationship: Defines a high-level, object-oriented link between two mapped database classes
from app.db.base import Base # Imports your custom, local declarative base class (typically built using DeclarativeBase) that all your database models must inherit from to be tracked by the ORM.


class TranscriptStatus(StrEnum):
    """Status of a transcript."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


class Channel(Base):
    __tablename__ = "channels" # The name of the table in the database.

    channel_id: Mapped[str] = mapped_column(String(64), primary_key=True)   # Mapped Says this is a column in the database ("Channel_id")
                                                                            # mapped_column is a function used to create the entire column. I think this is ORM being used 
                                                                            # String(64) is the length of the column in the database.
                                                                            # primary_key=True means that this column is the primary key of the table.
    label: Mapped[str] = mapped_column(String(255), default="") # default="" means that the column will be empty by default.
    created_at: Mapped[datetime] = mapped_column(           # "Mapped[datetime]" says this coulmn is a "datetime" data type
        DateTime(timezone=True), server_default=func.now()  # "Datetime()" is the time for ingestion? or time channel was last ingested?
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    videos: Mapped[list[Video]] = relationship(back_populates="channel")


class Video(Base):
    __tablename__ = "videos"

    video_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("channels.channel_id"), index=True
    )
    title: Mapped[str] = mapped_column(String(512), default="")
    url: Mapped[str] = mapped_column(String(512), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    transcript_status: Mapped[str] = mapped_column(
        String(32), default=TranscriptStatus.PENDING, index=True
    )
    transcript_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    channel: Mapped[Channel] = relationship(back_populates="videos")
    transcript: Mapped[Transcript | None] = relationship(
        back_populates="video", uselist=False
    )


class Transcript(Base):
    __tablename__ = "transcripts"

    video_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("videos.video_id"), primary_key=True
    )
    text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    video: Mapped[Video] = relationship(back_populates="transcript")


"""
All This file is for is to generate the tables for my postgresql database, and be able to vizualize them into my TablePlus application. 
It works because whenever I have my docker container which holds my Postgresql database running, I can generate tables with the data that is inside of it 
using TablePlus with my locally ran docker container (locally meaning it is ran on my computers memory and not some cloud server)
"""