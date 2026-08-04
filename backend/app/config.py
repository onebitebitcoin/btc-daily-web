from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./btc_daily.db"
    # Empty means "no publishing key configured" — auth must fail closed, never
    # ship a usable default secret.
    admin_api_key: str = ""
    og_cache_dir: str = "/data/og"
    img_cache_dir: str = "/data/img"


@lru_cache
def get_settings() -> Settings:
    return Settings()
