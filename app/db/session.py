"""Database session helpers."""

from __future__ import annotations

from collections.abc import Generator # 'Generator' types the return; yields a session, then finishes
from contextlib import contextmanager # Turns a generator into a with block helper

from sqlalchemy.orm import Session # SQLAlchemy ORM session type (tracks queries/changes)

from app.db.base import SessionLocal # Factory from base.py that creates each session


@contextmanager # Wraps get_session so you can write 'with get_session() as session:' . Code before yield runs on enter; code after yield runs on exit (commit/rollback/close).
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal() # Opens a session
    try:
        yield session # yields the session to my code
        session.commit() # commits multi-step operations if successful
    except Exception:
        session.rollback() # rolls back on error
        raise
    finally:
        session.close() # closes the session

# This function returns a context manager which allows you to control pieces of information from ingestion until we dont need it anymore. 
# It works by using the function within a 'with' statement, and within that with statement we can perform database operations on certain information in isolated sessions for a specific 'with' block. 
# It's about safe transaction boundaries, not holding ingest data in memory until you're 'done' with it. 
# ***REMEMBER*** Using sessions makes data ingestion so much more safer and reliable ***REMEMBER***

"""This file is basically the factory settings for each session"""