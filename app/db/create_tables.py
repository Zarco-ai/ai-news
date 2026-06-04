"""Create all database tables."""

from __future__ import annotations

import logging

from app.db.base import Base, engine
from app.db import models  # noqa: F401

logger = logging.getLogger(__name__)


def create_tables() -> None:
    '''Creates all the tables onto my Postgresql db'''
    Base.metadata.create_all(bind=engine) # Base is a template for our schema, we built the schema on "models.py", and now the schema/tables are registered in the metadata
                                            # The metadata has a method called "create_all()" which will allow us to build all of our databases tables
                                            # Whenever you tie your sqlalchemy "Base" (Table Models for Data Schema) to the connection pool to your relational sql database ("bind=engine") 
                                                # That is held in a docker container locally on your laptop
                                            # You are able to to get a visual representation of the data stored in your db (since my db is ran locally it uses my computers memory to run, and all of the data inside of this db is stored onto my SSD/Hardrive)
    logger.info("Database tables created.") # Printed in terminal/console whenever the databases are created


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s") 
    create_tables()

"""

This file is to create tables for my postgresql db onto an application called 'TablePlus':
By using docker to contain my db ran locally, I could connect this db to an application called "TablePlus" which could get a hold of my DB via ports, ids and passwords.
I was able to create the tables themselves using SQLAlchemy to register the data schemas in the metadata of a class called "Base" which could
create all of the tables in connection to our db using a parameter, "bind=engine", which gives us a low level connection pool to our local db. 
Because now that all of our data schema is translated from Python to SQL, our relational db is able to understand our scripts which created our SQL db's Tables on TablePlus, am I correct? 

"""
