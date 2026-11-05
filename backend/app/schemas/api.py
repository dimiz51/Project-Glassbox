from pydantic import BaseModel

from app.schemas.errors import ErrorOut


class OkOut(BaseModel):
    ok: bool = True


class SessionOut(BaseModel):
    session_id: str
    title: str
    created: float
    running: bool


class HealthOut(BaseModel):
    ok: bool
    provider: str  # openai | openrouter | ollama
    model: str
    url: str  # where the model runs
    error: ErrorOut | None = None  # ollama_unreachable | model_not_pulled | model_unavailable
