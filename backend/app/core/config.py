from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]  # project root (parent of backend/)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # LLM (Ollama via LangChain)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    ollama_num_ctx: int = 16384
    ollama_repeat_penalty: float = 1.1  # discourages repeating itself within one output
    ollama_think: bool = False  # thinking mode: smarter steps, but much slower
    use_vision: bool = True  # set false for text-only models

    # Sandbox browser
    headless: bool = True
    viewport_width: int = 1280
    viewport_height: int = 800
    max_steps: int = 30

    # Where screenshots + logs go: session_blob/{session_id}/
    blob_dir: Path = ROOT / "session_blob"


settings = Settings()
settings.blob_dir.mkdir(parents=True, exist_ok=True)
