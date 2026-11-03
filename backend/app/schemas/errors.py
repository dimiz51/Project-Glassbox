"""The error contract: what every error looks like on the wire (HTTP responses and websocket events)."""

from enum import StrEnum

from pydantic import BaseModel


class ErrorCode(StrEnum):
    OLLAMA_UNREACHABLE = "ollama_unreachable"
    MODEL_NOT_PULLED = "model_not_pulled"
    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_FAILED = "model_failed"
    MODEL_INVALID_OUTPUT = "model_invalid_output"
    BROWSER_ACTION_FAILED = "browser_action_failed"
    BROWSER_START_FAILED = "browser_start_failed"
    SESSION_NOT_FOUND = "session_not_found"
    AGENT_CRASHED = "agent_crashed"
    INVALID_REQUEST = "invalid_request"
    NOT_FOUND = "not_found"
    INTERNAL = "internal"


class ErrorOut(BaseModel):
    code: ErrorCode
    message: str
    hint: str | None = None
    detail: str | None = None

    model_config = {"json_schema_extra": {"examples": [{
        "code": "model_not_pulled",
        "message": "The model qwen3.5:9b isn't downloaded yet.",
        "hint": "Run `ollama pull qwen3.5:9b`, or set OLLAMA_MODEL in .env to a model you have.",
        "detail": None,
    }]}}
