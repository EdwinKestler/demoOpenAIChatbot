from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker
from decouple import config

DB_USER = config("DB_USER")
DB_PASSWORD = config("DB_PASSWORD")
DB_HOST = config("DB_HOST", default="localhost")
DB_PORT = int(config("DB_PORT", default=5432))

DB_CATALOG_USER = config("DB_CATALOG_USER")
DB_CATALOG_PASSWORD = config("DB_CATALOG_PASSWORD")
DB_CHAT_NAME = config("DB_CHAT_NAME", default="postgres")
DB_CATALOG_NAME = config("DB_CATALOG_NAME", default="my_catalog_db")

chat_url = URL.create(
    drivername="postgresql+psycopg2",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_CHAT_NAME,
)
chat_engine = create_engine(chat_url)
ChatSessionLocal = sessionmaker(bind=chat_engine, autoflush=False, autocommit=False)
ChatBase = declarative_base()

catalog_url = URL.create(
    drivername="postgresql+psycopg2",
    username=DB_CATALOG_USER,
    password=DB_CATALOG_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_CATALOG_NAME,
)
catalog_engine = create_engine(catalog_url)
CatalogSessionLocal = sessionmaker(bind=catalog_engine, autoflush=False, autocommit=False)
CatalogBase = declarative_base()