from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    APP_LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://rag:rag@localhost:5432/ragdb"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MinIO / S3
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "rag-documents"
    S3_REGION: str = "us-east-1"

    # Auth
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # LLM
    LLM_PROVIDER: str = "anthropic"  # "anthropic" | "openai" | "ollama"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-20250514"
    LLM_MAX_TOKENS: int = 1024
    LLM_TEMPERATURE: float = 0.1

    # Storage provider — "s3" (AWS S3 / MinIO) or "gcs" (Google Cloud Storage)
    STORAGE_PROVIDER: str = "s3"
    GCS_PROJECT_ID: str = ""
    GCS_BUCKET: str = ""  # falls back to S3_BUCKET when STORAGE_PROVIDER=s3

    # Ollama (local LLM + embeddings)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"

    # Embedding
    EMBEDDING_PROVIDER: str = "ollama"
    EMBEDDING_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIMENSION: int = 768

    # Ingestion
    CHUNK_SIZE_TOKENS: int = 512
    CHUNK_OVERLAP_TOKENS: int = 64
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_CONTENT_TYPES: str = "application/pdf,text/markdown,text/plain"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    CELERY_TASK_MAX_RETRIES: int = 3

    @property
    def allowed_content_types_list(self) -> list[str]:
        return [ct.strip() for ct in self.ALLOWED_CONTENT_TYPES.split(",")]

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        """Fail fast on startup if insecure defaults are used in production."""
        if self.is_production and self.JWT_SECRET_KEY == "change-me-in-production":
            raise ValueError(
                "JWT_SECRET_KEY must be changed from the default in production. "
                "Generate one with: openssl rand -hex 32"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
