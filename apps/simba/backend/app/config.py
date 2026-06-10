"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Solar PV Simulator"
    debug: bool = False
    data_dir: str = "/app/data"
    upload_dir: str = "/app/data/uploads"

    # Future: database, auth, API keys
    # database_url: str = "postgresql://..."
    # secret_key: str = "change-me"

    model_config = {"env_prefix": "PVTOOL_", "env_file": ".env"}


settings = Settings()
