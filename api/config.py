from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "EYE-Lead"
    environment: str = Field(default="dev")
    log_level: str = Field(default="INFO")

    # Gemini is invoked via Vertex AI using Application Default Credentials.
    # No API key needed — auth flows through google.auth.default().
    gemini_model: str = Field(default="gemini-2.5-flash")
    vertex_ai_location: str = Field(default="us-central1")

    google_cloud_project: str = Field(default="", description="GCP project ID")
    google_application_credentials: str = Field(
        default="", description="Path to service-account JSON for ADC"
    )

    earth_engine_project: str = Field(default="", description="EE Cloud project ID")
    earth_engine_service_account: str = Field(default="")
    earth_engine_private_key_file: str = Field(default="")

    google_solar_api_key: str = Field(default="", description="Solar/Maps Platform API key")
    census_api_key: str = Field(default="")
    nrel_api_key: str = Field(default="")


@lru_cache
def get_settings() -> Settings:
    return Settings()
