from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/innovateus"
    # OpenAI
    openai_api_key: str = ""
    # Auth
    jwt_secret: str = "change-me-in-production"
    # Salt for hashing IP addresses before storage. Kept separate from the
    # JWT secret so rotating one does not invalidate the other (rotating
    # the JWT secret used to reset every analytics IP hash).
    # Falls back to ``jwt_secret`` when unset for backward compatibility
    # with deployments that haven't been migrated yet.
    ip_hash_salt: str = ""
    # HMAC secret used to mint per-submission session tokens. Falls back
    # to ``jwt_secret`` when unset. Rotating this invalidates every
    # in-flight submission token (acceptable — surveys are short).
    submission_token_secret: str = ""
    admin_password_hash: str = ""
    editor_password_hash: str = ""
    # Qualtrics
    qualtrics_api_token: str = ""
    qualtrics_production_survey_id: str = ""
    qualtrics_production_datacenter_id: str = ""
    qualtrics_test_survey_id: str = ""
    qualtrics_test_datacenter_id: str = ""
    qualtrics_default_target: str = "production"  # "production" | "test" | "none"
    # Deprecated single-survey vars — fall through to test slot when set
    qualtrics_survey_id: str = ""
    qualtrics_datacenter_id: str = ""
    # JotForm
    jotform_api_key: str = ""
    jotform_form_id: str = ""
    jotform_api_url: str = "https://api.jotform.com"
    # OpenAI Models
    openai_model_vagueness: str = "gpt-5"
    openai_model_followups: str = "gpt-5"
    openai_model_extraction: str = "gpt-5"
    openai_model_cleanup: str = "gpt-5"
    openai_model_pii: str = "gpt-5-mini"
    openai_model_transcription: str = "gpt-4o-transcribe"
    # App
    cors_origins: str = "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003"
    environment: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore", "env_ignore_empty": True}

    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url


_settings_instance = None


_INSECURE_JWT_DEFAULTS = {"", "change-me-in-production"}


def _validate_production(s: "Settings") -> None:
    """Refuse to start the app in production with placeholder/default secrets.

    Catches the case where ``JWT_SECRET`` (or the database URL) is missing in
    the deployment environment — without this, tokens would be signed with a
    publicly-known default and could be forged by anyone reading the source.
    """
    if s.environment == "development":
        return
    problems: list[str] = []
    if s.jwt_secret in _INSECURE_JWT_DEFAULTS:
        problems.append("JWT_SECRET is unset or uses the placeholder default")
    if "postgres:postgres@localhost" in s.database_url:
        problems.append("DATABASE_URL is unset or uses the local development default")
    if not s.admin_password_hash:
        problems.append("ADMIN_PASSWORD_HASH is not configured")
    if problems:
        raise RuntimeError(
            "Refusing to start in non-development environment with insecure config: "
            + "; ".join(problems)
        )


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
        _validate_production(_settings_instance)
    return _settings_instance
