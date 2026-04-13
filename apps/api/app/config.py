from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/innovateus"
    # OpenAI
    openai_api_key: str = ""
    # Auth
    jwt_secret: str = "change-me-in-production"
    admin_password_hash: str = ""
    editor_password_hash: str = ""
    # Qualtrics
    qualtrics_api_token: str = ""
    qualtrics_survey_id: str = ""
    qualtrics_datacenter_id: str = ""
    # JotForm
    jotform_api_key: str = ""
    jotform_form_id: str = ""
    jotform_api_url: str = "https://api.jotform.com"
    # OpenAI Models
    openai_model_vagueness: str = "gpt-4.1-nano"
    openai_model_followups: str = "gpt-4.1-mini"
    openai_model_extraction: str = "gpt-4.1"
    openai_model_cleanup: str = "gpt-4.1-nano"
    openai_model_transcription: str = "whisper-1"
    # App
    cors_origins: str = "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003"
    environment: str = "development"

    model_config = {"env_file": "../../.env", "env_file_encoding": "utf-8", "extra": "ignore", "env_ignore_empty": True}

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url


_settings_instance = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
