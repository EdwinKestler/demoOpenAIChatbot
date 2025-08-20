# app/database.py
# ------------------------------------------------------------
# PostgreSQL SQLAlchemy setup (explicit psycopg2 driver)
# - CHANGED: read all params from env via decouple
# - CHANGED: explicit driver "postgresql+psycopg2"
# - ADDED: safer sessionmaker flags (autoflush=False, autocommit=False)
# - REMOVED: Base.metadata.create_all(engine) at import time (moved to FastAPI @startup)
# ------------------------------------------------------------
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker
from decouple import config

# ADDED: get DB params from environment (you already validated these with your test script)
DB_USER = config("DB_USER")                                # e.g. "postgres"
DB_PASSWORD = config("DB_PASSWORD")                        # your password
DB_HOST = config("DB_HOST", default="localhost")           # default matches local dev
DB_PORT = int(config("DB_PORT", default=5432))             # converts to int
DB_NAME = config("DB_NAME", default="postgres")            # default db name

# CHANGED: explicit drivername to match psycopg2-binary in requirements.txt
url = URL.create(
    drivername="postgresql+psycopg2",                      # CHANGED from "postgresql"
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
)

# NOTE: if you ever need to force client encoding:
# engine = create_engine(url, connect_args={"options": "-c client_encoding=utf8"})
engine = create_engine(url)                                 # unchanged behavior otherwise

# CHANGED: safer session defaults
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)  # CHANGED flags

Base = declarative_base()

# REMOVED: DO NOT create tables at import time; this caused early crashes with uvicorn reload
# Base.metadata.create_all(engine)  # REMOVED (now done inside FastAPI @startup)
