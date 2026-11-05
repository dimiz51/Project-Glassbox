"""Domain errors: one exception class per error, each tied to an ErrorCode and carrying an
ErrorOut (app/schemas/errors.py): a human `message`, a `hint` on what to do next, and an
optional technical `detail`.

No HTTP here: app/api/errors.py translates codes to status codes. Agent errors travel over the
websocket as events with the same ErrorOut shape.
"""

import httpx
import openai
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.errors import ErrorCode, ErrorOut


def _first_line(e: BaseException | None) -> str | None:
    if e is None:
        return None
    return (str(e).strip().splitlines() or [type(e).__name__])[0][:300]


class DomainError(Exception):
    code: ErrorCode

    def __init__(self, message: str, hint: str | None = None, detail: str | None = None):
        super().__init__(message)
        self.out = ErrorOut(code=self.code, message=message, hint=hint, detail=detail)


# ---- model (OpenAI, OpenRouter or Ollama) --------------------------------------

CLOUD = {  # provider -> (display name, its .env variables)
    "openai": ("OpenAI", "OPENAI_API_KEY and OPENAI_MODEL"),
    "openrouter": ("OpenRouter", "OPENROUTER_API_KEY and OPENROUTER_MODEL"),
}


class ModelUnavailable(DomainError):
    """The cloud provider refused or can't be reached: bad key, unknown model, no credit left."""

    code = ErrorCode.MODEL_UNAVAILABLE

    def __init__(self, cause: BaseException | None = None):
        name, env = CLOUD[settings.provider]
        super().__init__(
            f"{name} can't run {settings.model}.",
            hint=f"Check {env} in .env (and your {name} credits), or remove them to use Ollama.",
            detail=_first_line(cause),
        )


class OllamaUnreachable(DomainError):
    code = ErrorCode.OLLAMA_UNREACHABLE

    def __init__(self, cause: BaseException | None = None):
        super().__init__(
            "Can't reach Ollama.",
            hint="Start it with `ollama serve` (or open the Ollama app), then try again.",
            detail=f"{settings.ollama_base_url}: {_first_line(cause)}" if cause else settings.ollama_base_url,
        )


class ModelNotPulled(DomainError):
    code = ErrorCode.MODEL_NOT_PULLED

    def __init__(self):
        super().__init__(
            f"The model {settings.ollama_model} isn't downloaded yet.",
            hint=f"Run `ollama pull {settings.ollama_model}`, or set OLLAMA_MODEL in .env to a model you have.",
        )


class ModelInvalidOutput(DomainError):
    code = ErrorCode.MODEL_INVALID_OUTPUT

    def __init__(self, cause: BaseException):
        super().__init__("The model replied with something that wasn't a valid action.",
                         hint="The agent asks again automatically.", detail=_first_line(cause))


class ModelFailed(DomainError):
    code = ErrorCode.MODEL_FAILED

    def __init__(self, cause: BaseException):
        super().__init__("The model call failed.", hint="The agent retries on the next step.",
                         detail=_first_line(cause))


def from_model_error(e: BaseException) -> DomainError:
    """Turn whatever the LangChain model call raised into a typed error."""
    if settings.provider in CLOUD:  # both go through the openai client, so they raise the same errors
        unusable = (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError,
                    openai.APIConnectionError)
        out_of_credit = (isinstance(e, openai.RateLimitError) and "insufficient_quota" in str(e)) or (
            isinstance(e, openai.APIStatusError) and e.status_code == 402)  # OpenRouter: no credits left
        if isinstance(e, unusable) or out_of_credit:
            return ModelUnavailable(e)
    else:
        if isinstance(e, (httpx.ConnectError, ConnectionError)):
            return OllamaUnreachable(e)
        text = str(e).lower()
        if "not found" in text and ("model" in text or settings.ollama_model in text):
            return ModelNotPulled()
    if isinstance(e, (ValidationError, ValueError)):
        return ModelInvalidOutput(e)
    return ModelFailed(e)


# ---- sandbox browser ----------------------------------------------------------

class BrowserStartFailed(DomainError):
    code = ErrorCode.BROWSER_START_FAILED

    def __init__(self, cause: BaseException):
        super().__init__("Couldn't start a sandbox browser.",
                         hint="Check the backend logs (`docker compose logs backend`), then try again.",
                         detail=_first_line(cause))


class BrowserActionFailed(DomainError):
    code = ErrorCode.BROWSER_ACTION_FAILED

    def __init__(self, what: str, cause: BaseException):
        super().__init__(f"Couldn't {what}.", hint="The agent will try another way.", detail=_first_line(cause))


# ---- sessions & agent -----------------------------------------------------------

class SessionNotFound(DomainError):
    code = ErrorCode.SESSION_NOT_FOUND

    def __init__(self, sid: str):
        super().__init__("This chat no longer exists.",
                         hint="The server was probably restarted. Start a new chat.", detail=f"session {sid}")


class AgentCrashed(DomainError):
    code = ErrorCode.AGENT_CRASHED

    def __init__(self, cause: BaseException):
        super().__init__(
            "The agent stopped unexpectedly.",
            hint="Send your prompt again, or start a new chat. Details are in session_blob/{id}/log.jsonl.",
            detail=f"{type(cause).__name__}: {_first_line(cause)}",
        )
