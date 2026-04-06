from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # AWS
    aws_region: str = "us-east-1"
    dynamodb_endpoint_url: str = ""  # Set to "http://localhost:8000" for DynamoDB Local
    surveys_table_name: str = "innovateus-surveys"
    submissions_table_name: str = "innovateus-submissions"
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
    # App
    cors_origins: str = "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003"
    environment: str = "development"

    model_config = {"env_file": "../../.env", "env_file_encoding": "utf-8", "extra": "ignore", "env_ignore_empty": True}


_settings_instance = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
