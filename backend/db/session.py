import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from backend.env import load_project_env


DEFAULT_DATABASE_URL = "sqlite:///./crisisagent.db"


def _load_database_env() -> None:
    load_project_env()


_load_database_env()


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def is_database_checkpoint_enabled() -> bool:
    storage = os.getenv("CHECKPOINT_STORAGE", "json").strip().lower()
    return storage in {"postgres", "postgresql", "database", "db", "sqlalchemy"}


@lru_cache(maxsize=1)
def get_engine():
    return create_engine(get_database_url(), future=True)


@lru_cache(maxsize=1)
def get_session_factory():
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)


def get_db_session():
    session_factory = get_session_factory()
    with session_factory() as session:
        yield session
