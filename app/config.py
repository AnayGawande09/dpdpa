from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = "sqlite+aiosqlite:///./dpdp.db"
    SECRET_KEY: str = "change-this-demo-secret-key-in-production"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 10


settings = Settings()
