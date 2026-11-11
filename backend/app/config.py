from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")
    environment: str = "development"
    database_url: str | None = None
    postgres_host: str = "db"
    postgres_db: str = "istay"
    postgres_user: str = "istay"
    postgres_password: str = ""
    postgres_password_file: str | None = None
    app_origin: str = "http://localhost:8081"
    secure_cookies: bool = False
    session_hours: int = 12
    trusted_hosts: str = "localhost,127.0.0.1,api,testserver"

    @model_validator(mode="after")
    def production_guards(self):
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("Unsupported environment")
        if self.environment == "production":
            if not self.secure_cookies or not self.app_origin.startswith("https://"):
                raise ValueError("Production requires HTTPS origin and Secure cookies")
            if "*" in self.trusted_hosts:
                raise ValueError("Production requires explicit trusted hosts")
            if not self.postgres_password_file:
                raise ValueError("Production requires a database password file")
        return self

    def db_url(self):
        if self.database_url and self.environment != "production":
            return self.database_url
        password = (
            Path(self.postgres_password_file).read_text().strip()
            if self.postgres_password_file
            else self.postgres_password
        )
        if not password:
            raise ValueError("Database password is required")
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=password,
            host=self.postgres_host,
            database=self.postgres_db,
        )


@lru_cache
def settings():
    return Settings()
