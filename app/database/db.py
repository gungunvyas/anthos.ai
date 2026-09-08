import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

engine = None
SessionLocal = None

if DATABASE_URL and DATABASE_URL != "X10":
    try:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    except Exception:
        pass


def get_db():
    global engine, SessionLocal
    if SessionLocal is None:
        db_url = os.getenv("DATABASE_URL")
        if not db_url or db_url == "X10":
            raise RuntimeError(
                "DATABASE_URL is not set or is still a placeholder. "
                "Please configure DATABASE_URL in your environment variables or deployment secrets (refer to .env.sample)."
            )
        engine = create_engine(db_url, pool_pre_ping=True)
        SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
