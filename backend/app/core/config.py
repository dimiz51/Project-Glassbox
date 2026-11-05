from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]  # project root (parent of backend/)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # LLM (via LangChain): a cloud provider when its key + model pair is set (OpenAI wins if both are),
    # otherwise Ollama on your machine
    openai_api_key: str | None = None
    openai_model: str | None = None
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None  # OpenRouter id, e.g. qwen/qwen3-vl-32b-instruct
    openrouter_base_url: str = "https://openrouter.ai/api/v1"  # speaks the OpenAI API
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:9b"
    ollama_num_ctx: int = 16384
    ollama_repeat_penalty: float = 1.1  # discourages repeating itself within one output
    ollama_think: bool = False  # thinking mode: smarter steps, but much slower
    history_messages: int = 10  # rolling window of the step conversation sent to the model
    history_images: int = 3  # the newest screenshots sent as images (current screen + earlier ones); older are text

    # Sandbox browser
    headless: bool = True
    viewport_width: int = 1280
    viewport_height: int = 800
    max_steps: int = 30

    # Tracing (Langfuse): off unless both keys are set
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # Where screenshots + logs go: session_blob/{session_id}/
    blob_dir: Path = ROOT / "session_blob"

    @property
    def provider(self) -> str:
        if self.openai_api_key and self.openai_model:
            return "openai"
        if self.openrouter_api_key and self.openrouter_model:
            return "openrouter"
        return "ollama"

    @property
    def model(self) -> str:
        """The model in use, whichever provider it is."""
        return {"openai": self.openai_model, "openrouter": self.openrouter_model}.get(self.provider, self.ollama_model)


settings = Settings()
settings.blob_dir.mkdir(parents=True, exist_ok=True)
