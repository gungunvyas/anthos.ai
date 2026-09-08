from functools import lru_cache

from pydantic_settings import SettingsConfigDict,BaseSettings


class Settings(BaseSettings):

    GOOGLE_API_KEY: str| None = None 
    DATABASE_URL: str
    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()