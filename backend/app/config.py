from functools import lru_cache
from secrets import token_urlsafe

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://packwise:packwise@localhost:5432/packwise"
    secret_key: str = Field(default_factory=lambda: token_urlsafe(48), min_length=32)
    access_token_minutes: int = 120
    cors_origins: list[str] = ["http://localhost:8080", "http://127.0.0.1:8080"]
    # "flutter run -d chrome" binds the web dev server to a different random port
    # on every launch, so a fixed allow-list in cors_origins constantly falls out
    # of sync with reality and every request gets silently blocked by CORS (which
    # the Flutter client can only report as a generic "cannot reach API" error).
    # In development we additionally allow any localhost/127.0.0.1 port via a
    # regex; production must keep using the explicit cors_origins allow-list.
    cors_origin_regex: str | None = None
    seed_demo: bool = False
    demo_password: str | None = None
    model_directory: str = "./models"
    model_adapter: str = ""

    @model_validator(mode="after")
    def production_settings(self):
        if self.app_env == "production":
            if "secret_key" not in self.model_fields_set:
                raise ValueError("SECRET_KEY must be configured in production")
            if self.seed_demo:
                raise ValueError("Demo seeding must be disabled in production")
        elif self.cors_origin_regex is None:
            self.cors_origin_regex = r"^https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$"
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
