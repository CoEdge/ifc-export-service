import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "ifc-export-service"
    APP_VERSION: str = (Path(__file__).parent.parent / "VERSION").read_text().strip()
    PORT: int = 8004
    MODELING_SERVICE_URL: str = "http://localhost:8003"
    LOG_LEVEL: str = "INFO"

    model_config = {"env_prefix": "", "case_sensitive": True}


settings = Settings()
