"""Database configuration from environment."""

from __future__ import annotations

import os
from functools import lru_cache # functools is a standard library for higher-order functions on callables

from dotenv import load_dotenv

load_dotenv()

# Local dev fallback only. In production DATABASE_URL is always provided by the
# host (Render), so this default is never used there.
DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://ai_news:ai_news_dev_password@localhost:5432/ai_news"
)


def _normalize_url(url: str) -> str:
    """Make a host-provided URL usable by SQLAlchemy + psycopg v3.

    Render (and others) hand out URLs starting with `postgres://`, but
    SQLAlchemy needs an explicit driver: `postgresql+psycopg://`.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


@lru_cache # This will allow for the Database URL to be cached so .env is read once; later calls reuse the same URL without reparsing
def get_database_url() -> str:
    raw = os.getenv("DATABASE_URL")
    if not raw:
        # No env var: only acceptable for local development.
        if os.getenv("ENV", "development") == "production":
            raise RuntimeError("DATABASE_URL must be set in production")
        return DEFAULT_DATABASE_URL
    return _normalize_url(raw)

"""This file is just to get the database url, normalize its scheme for psycopg, and cache it."""
