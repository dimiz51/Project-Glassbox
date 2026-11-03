"""HTTP translator: domain errors -> HTTP status codes + ErrorOut JSON.

Every error response of the API has the ErrorOut shape, including request validation errors,
unknown routes and unexpected crashes. The status codes live here and nowhere else.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import DomainError
from app.schemas.errors import ErrorCode, ErrorOut

log = logging.getLogger("uvicorn.error")

HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.INVALID_REQUEST: 422,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.SESSION_NOT_FOUND: 404,
    ErrorCode.OLLAMA_UNREACHABLE: 503,  # a dependency is down, retry later
    ErrorCode.MODEL_NOT_PULLED: 503,
    ErrorCode.BROWSER_START_FAILED: 503,
    ErrorCode.MODEL_FAILED: 502,  # the upstream model misbehaved
    ErrorCode.MODEL_INVALID_OUTPUT: 502,
    ErrorCode.BROWSER_ACTION_FAILED: 500,
    ErrorCode.AGENT_CRASHED: 500,
    ErrorCode.INTERNAL: 500,
}


def status_for(code: ErrorCode) -> int:
    return HTTP_STATUS.get(code, 500)


def error_responses(*codes: ErrorCode) -> dict:
    """OpenAPI `responses=` for a route: documents which typed errors it can return."""
    out: dict[int, dict] = {}
    for code in codes:
        entry = out.setdefault(status_for(code), {"model": ErrorOut, "description": ""})
        entry["description"] = ", ".join(filter(None, [entry["description"], f"`{code}`"]))
    return out


def _json(out: ErrorOut) -> JSONResponse:
    return JSONResponse(status_code=status_for(out.code), content=out.model_dump(mode="json"))


def install(app: FastAPI):
    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError):
        return _json(exc.out)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []))
        return _json(ErrorOut(code=ErrorCode.INVALID_REQUEST, message="The request is invalid.",
                              hint="Check the request body against /api/docs.",
                              detail=f"{where}: {first.get('msg', '')}".strip(": ")))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return _json(ErrorOut(code=ErrorCode.NOT_FOUND, message="This endpoint doesn't exist.",
                                  hint="See /api/docs for the available endpoints.", detail=str(exc.detail)))
        out = ErrorOut(code=ErrorCode.INTERNAL, message="The request failed.", detail=str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=out.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.exception("unhandled error")
        return _json(ErrorOut(code=ErrorCode.INTERNAL, message="Something went wrong on the server.",
                              hint="Try again. If it keeps happening, check `docker compose logs backend`.",
                              detail=f"{type(exc).__name__}: {exc}"[:300]))
