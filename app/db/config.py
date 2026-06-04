"""Database configuration from environment."""

from __future__ import annotations

import os
from functools import lru_cache # functools is a standard library for higher-order functions on callables

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://ai_news:ai_news_dev_password@localhost:5432/ai_news"
)


@lru_cache # This will allow for the Database URL to be cached so .env is read once; later calls reuse the same URL without reparsing
def get_database_url() -> str: 
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

"""This file is just to get the database url and cache it with either the actual database url or just a default url."""
