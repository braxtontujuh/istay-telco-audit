import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.config import settings
from app.db import get_db
from app.main import app
from app.models import Site, User, UserSiteAccess
from app.security import hasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

PASSWORD = "test-only-long-password"


@pytest.fixture
def database():
    test_url = os.environ.get("TEST_POSTGRES_URL")
    schema_name = None
    admin_engine = None
    if test_url:
        url = make_url(test_url)
        if url.database != "istay_test":
            raise RuntimeError("PostgreSQL tests are restricted to the disposable istay_test database")
        schema_name = "test_" + uuid4().hex
        admin_engine = create_engine(url)
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema_name},public"})
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    with Session(engine) as db:
        db.add_all([Site(id=1, code="ONE", name="One"), Site(id=2, code="TWO", name="Two")])
        db.add_all(
            [
                User(
                    id=1,
                    username="admin",
                    full_name="Admin",
                    role="ADMIN",
                    password_hash=hasher.hash(PASSWORD),
                ),
                User(
                    id=2,
                    username="auditor",
                    full_name="Auditor",
                    role="AUDITOR",
                    password_hash=hasher.hash(PASSWORD),
                ),
                User(
                    id=3,
                    username="manager",
                    full_name="Manager",
                    role="MANAGER",
                    password_hash=hasher.hash(PASSWORD),
                ),
            ]
        )
        db.flush()
        db.add_all([UserSiteAccess(user_id=2, site_id=1), UserSiteAccess(user_id=3, site_id=2)])
        if test_url:
            # Explicit fixture IDs do not advance PostgreSQL sequences.
            for table in ("sites", "users"):
                db.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}))"
                    )
                )
        db.commit()
    try:
        yield engine
    finally:
        engine.dispose()
        if admin_engine is not None:
            with admin_engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema_name}" CASCADE'))
            admin_engine.dispose()


@pytest.fixture
def client(database, monkeypatch):
    monkeypatch.setenv("APP_ORIGIN", "http://testserver")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SECURE_COOKIES", "false")
    settings.cache_clear()

    def override():
        with Session(database, expire_on_commit=False) as db:
            yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    settings.cache_clear()


def login(client, username="admin"):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]
