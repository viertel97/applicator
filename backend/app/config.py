from cryptography.fernet import Fernet, InvalidToken
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    app_secret_key: str
    ms_tenant_id: str = ""
    ms_client_id: str = ""
    ms_client_secret: str = ""
    ms_redirect_uri: str = "http://localhost:8000/api/auth/callback"
    llm_provider: str = "groq"
    llm_model: str = "gpt-oss"
    llm_api_key: str
    llm_base_url: str = "https://api.groq.com/openai/v1"
    data_dir: str = "./data"
    frontend_origin: str = "http://localhost:5173"
    session_cookie_name: str = "applicator_session"
    session_cookie_secure: bool = False
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    @property
    def oauth_enabled(self) -> bool:
        return bool(self.ms_tenant_id and self.ms_client_id and self.ms_client_secret)

    @field_validator("celery_broker_url", mode="before")
    @classmethod
    def _default_broker(cls, v, info):
        return v or info.data.get("redis_url")

    @field_validator("celery_result_backend", mode="before")
    @classmethod
    def _default_backend(cls, v, info):
        return v or info.data.get("redis_url")

    @field_validator("app_secret_key")
    @classmethod
    def _validate_fernet_key(cls, v: str) -> str:
        """Fail fast at startup if the key is not a valid Fernet key.

        A valid Fernet key is a URL-safe base64-encoded 32-byte value (44 chars).
        Generate one with:
            python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
        """
        try:
            Fernet(v.encode())
        except (ValueError, InvalidToken, Exception) as exc:
            raise ValueError(
                f"APP_SECRET_KEY is not a valid Fernet key: {exc}. "
                "Generate one with: "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            ) from exc
        return v


def get_settings() -> Settings:
    return Settings()
