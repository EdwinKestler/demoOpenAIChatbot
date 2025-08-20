import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")

if DB_USER and DB_PASSWORD:
    try:
        conn = psycopg2.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            connect_timeout=5,
        )
        conn.close()
        print("PostgreSQL connection successful.")
    except Exception as exc:
        print(f"PostgreSQL connection failed: {exc}")
else:
    print("DB_USER or DB_PASSWORD environment variables are not set.")
