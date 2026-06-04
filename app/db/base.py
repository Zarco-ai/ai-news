"""SQLAlchemy engine and declarative base."""

from __future__ import annotations

from sqlalchemy import create_engine # Builds the DB connection pool
from sqlalchemy.orm import DeclarativeBase, sessionmaker # Base class for ORM models, and Factory that creates Session objects bound to the engine

from app.db.config import get_database_url


class Base(DeclarativeBase): # DeclarativeBase : Empty base class; subclasses (Channel, Video, …) register table metadata on Base.metadata so SQLAlchemy knows your schema.
    pass                    


engine = create_engine(get_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False) # bind=engine ties sessions to your DB
                                                                                     # autoflush=False / autocommit=False = you control when changes flush and commit (via get_session() )
                                                                                        # They are set to Flase because in "session.py", we control the factory settings (commit, rollback, and close)

"""
This file is basically for configuring your session Factory (SessionLocal) for ORM by getting your engine to connect to your relational db,
and setting the parent class for ALL future Table Models by declaring a base model for a class called "Base".
"""
