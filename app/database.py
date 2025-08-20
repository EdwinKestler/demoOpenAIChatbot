from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker
from decouple import config

url = URL.create(
    drivername="postgresql",
    username=config("DB_USER"),
    password=config("DB_PASSWORD"),
    host="localhost",
    database="mydb",
    port=5432,
)

engine = create_engine(url)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

Base.metadata.create_all(engine)
