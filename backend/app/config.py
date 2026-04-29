from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    app_secret_key: str
    ms_tenant_id: str
    ms_client_id: str
    ms_client_secret: str
    ms_redirect_uri: str
    llm_provider: str = "groq"
    llm_model: str = "gpt-oss"
    llm_api_key: str
    llm_base_url: str = "https://api.groq.com/openai/v1"
    data_dir: str = "./data"
    frontend_origin: str = "http://localhost:5173"
    session_cookie_name: str = "applicator_session"
    session_cookie_secure: bool = False


def get_settings() -> Settings:
    return Settings()
