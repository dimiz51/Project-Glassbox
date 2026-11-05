import httpx
from fastapi import APIRouter

from app.core import errors
from app.core.config import settings
from app.schemas.api import HealthOut

router = APIRouter(tags=["health"])

OPENAI_URL = "https://api.openai.com/v1"


@router.get("/health", response_model=HealthOut, summary="Check the model provider and the model")
async def health():
    """Always 200. `ok` is false and `error` says why when the provider can't run the model:
    Ollama down or the model not pulled, or OpenAI / OpenRouter rejecting the key or the model."""
    if settings.provider == "openai":
        url, error = OPENAI_URL, await _check_openai()
    elif settings.provider == "openrouter":
        url, error = settings.openrouter_base_url, await _check_openrouter()
    else:
        url, error = settings.ollama_base_url, await _check_ollama()
    return HealthOut(ok=error is None, provider=settings.provider, model=settings.model, url=url, error=error)


async def _check_ollama():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            tags = (await client.get(f"{settings.ollama_base_url}/api/tags")).json()
        names = {m["name"] for m in tags.get("models", [])}
        if not ({settings.ollama_model, f"{settings.ollama_model}:latest"} & names):
            return errors.ModelNotPulled().out
    except Exception as e:
        return errors.OllamaUnreachable(e).out


async def _check_openai():
    """The model's metadata endpoint: checks the key and the model name, costs nothing."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OPENAI_URL}/models/{settings.openai_model}",
                                 headers={"Authorization": f"Bearer {settings.openai_api_key}"})
        if r.status_code != 200:
            return errors.ModelUnavailable(Exception(f"HTTP {r.status_code}: {r.text[:200]}")).out
    except Exception as e:
        return errors.ModelUnavailable(e).out


async def _check_openrouter():
    """Two free calls: the key endpoint (401 on a bad key) and the model's public metadata (404 if unknown),
    which also says whether the model takes images."""
    base = settings.openrouter_base_url
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{base}/key", headers={"Authorization": f"Bearer {settings.openrouter_api_key}"})
            if r.status_code != 200:
                return errors.ModelUnavailable(Exception(f"key check: HTTP {r.status_code}: {r.text[:200]}")).out
            r = await client.get(f"{base}/models/{settings.openrouter_model}/endpoints")
            if r.status_code != 200:
                return errors.ModelUnavailable(Exception(f"unknown model: HTTP {r.status_code}: {r.text[:200]}")).out
            if "image" not in r.json().get("data", {}).get("architecture", {}).get("input_modalities", ["image"]):
                return errors.ModelUnavailable(Exception("this model doesn't take images; pick a vision model")).out
    except Exception as e:
        return errors.ModelUnavailable(e).out
