from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import errors as http_errors
from app.api.router import api_router
from app.core.config import settings
from app.services import browser, sessions, tracing

DESCRIPTION = """
A vision model (local Ollama, OpenAI or OpenRouter) drives a sandboxed Chromium to answer prompts.

**Errors**: every error response is an `ErrorOut`: a fixed `code`, a human `message`, a `hint`
on what to do next, and an optional technical `detail`. Agent errors arrive as websocket events
with the same shape.
"""

TAGS = [
    {"name": "health", "description": "Can the model provider (Ollama, OpenAI or OpenRouter) run the configured model?"},
    {
        "name": "sessions",
        "description": """Each session has its own sandbox browser, chat history and event log.

**Websockets** (not modeled by OpenAPI):

`WS /api/sessions/{id}/chat`: talk to the agent. On connect, the session's past events are replayed.
- send `{"type": "prompt", "text": "..."}`: start a task, or steer the running one
- send `{"type": "stop"}`: stop the running task
- receive events: `user` · `start` · `observe` · `action` · `message` · `answer` · `stopped` ·
  `error` (`{"fatal": bool, "error": ErrorOut}`)

`WS /api/sessions/{id}/live`: read-only live view, receive `{"img": "<base64 jpeg>", "url": "..."}` frames.
Only the agent controls the browser; messages sent to this socket are ignored.
""",
    },
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await sessions.close_all()
    await browser.shutdown()
    tracing.shutdown()


app = FastAPI(
    title="Project Glassbox",
    version="0.1.0",
    description=DESCRIPTION,
    openapi_tags=TAGS,
    lifespan=lifespan,
    # under /api so they also work through the UI's proxy at :3000
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
http_errors.install(app)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(api_router)
# step screenshots: session_blob/{session_id}/*.png
app.mount("/api/blob", StaticFiles(directory=settings.blob_dir), name="blob")
