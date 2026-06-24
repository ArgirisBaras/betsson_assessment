"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Central configuration loaded from environment / .env file."""

    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model name")
    llm_enabled: bool = Field(default=True, description="Enable outbound chat LLM calls")
    log_level: str = Field(default="INFO", description="Logging level")
    chroma_path: str = Field(default="./chroma_data", description="ChromaDB persist dir")
    app_host: str = Field(default="0.0.0.0", description="FastAPI host")
    app_port: int = Field(default=8000, description="FastAPI port")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

