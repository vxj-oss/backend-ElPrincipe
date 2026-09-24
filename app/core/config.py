from typing import List
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_NAME: str = "El Príncipe - Agente de Ventas"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    COOKIE_NAME: str = "access_token"

    LOGIN_MAX_ATTEMPTS: int = 3
    LOGIN_LOCKOUT_MINUTES: int = 15

    LLM_PROVIDER: str = "ollama"


    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    FRONTEND_URL: str = "http://localhost:5173"
    FIRST_SUPERUSER: str = "admin"
    FIRST_SUPERUSER_PASSWORD: str
    SEED_ASESOR_USERNAME: str = "asesor1"
    SEED_ASESOR_PASSWORD: str

    @computed_field
    @property
    def IS_PRODUCTION(self) -> bool:
        return self.ENVIRONMENT == "production"

    @computed_field
    @property
    def CORS_ORIGINS(self) -> List[str]:
        if self.IS_PRODUCTION:
            return [self.FRONTEND_URL]
        return [
            self.FRONTEND_URL,
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]

    @computed_field
    @property
    def COOKIE_SAMESITE(self) -> str:
        return "none" if self.ENVIRONMENT == "production" else "lax"

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        if self.DATABASE_URL.startswith("postgresql://"):
            return self.DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
        return self.DATABASE_URL


settings = Settings()