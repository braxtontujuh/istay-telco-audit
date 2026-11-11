from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


@lru_cache
def engine():
    return create_engine(settings().db_url(), pool_pre_ping=True, hide_parameters=True)


def get_db():
    with sessionmaker(bind=engine(), expire_on_commit=False)() as db:
        yield db
