from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Research Assistant"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql://user:password@localhost:5432/research_assistant"
    REDIS_URL: str = "redis://localhost:6379"
    OPENAI_API_KEY: str = ""
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    SECRET_KEY: str = "fallback-secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    GEMINI_API_KEY: str = ""

    class Config:
        env_file = ".env"


settings = Settings()