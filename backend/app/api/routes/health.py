import httpx
from fastapi import APIRouter

from app.core import errors
from app.core.config import settings
from app.schemas.api import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut, summary="Check Ollama and the model")
async def health():
    """Always 200. `ok` is false and `error` says why when Ollama is down or the model isn't pulled."""
    error = None
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            tags = (await client.get(f"{settings.ollama_base_url}/api/tags")).json()
        names = {m["name"] for m in tags.get("models", [])}
        if not ({settings.ollama_model, f"{settings.ollama_model}:latest"} & names):
            error = errors.ModelNotPulled().out
    except Exception as e:
        error = errors.OllamaUnreachable(e).out
    return HealthOut(ok=error is None, model=settings.ollama_model, ollama_url=settings.ollama_base_url, error=error)
