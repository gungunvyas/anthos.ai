from functools import lru_cache

from pydantic_settings import SettingsConfigDict, BaseSettings


class Settings(BaseSettings):
    GOOGLE_API_KEY: str | None = None
    DATABASE_URL: str | None = None
    ANTHOSWEB_URL: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        raw_url = self.ANTHOSWEB_URL or "http://localhost:3000"
        return [origin.strip().rstrip("/") for origin in raw_url.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
