"""Optional Langfuse tracing. Off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set.

One trace per task, grouped by chat session:

    task (prompt in, answer out)
      step N
        decide    the model call: the exact messages + screenshot the model saw, and its raw reply
        <action>  the browser action and what happened
"""

from contextlib import contextmanager, nullcontext

from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

from app.core.config import settings


class _Noop:
    def update(self, **_):
        pass


_NOOP = _Noop()
_client = (
    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_base_url,
    )
    if settings.langfuse_public_key and settings.langfuse_secret_key
    else None
)


@contextmanager
def task(session_id: str, prompt: str):
    """The root of one trace. Call `.update(output=...)` on it with the final answer."""
    if not _client:
        yield _NOOP
        return
    with (
        propagate_attributes(session_id=session_id, trace_name="task", tags=[settings.provider, settings.model]),
        _client.start_as_current_observation(name="task", as_type="agent", input=prompt) as root,
    ):
        yield root


def span(name: str, **kwargs):
    """A child of whatever span is current, e.g. span("click", as_type="tool", input=...)."""
    return _client.start_as_current_observation(name=name, **kwargs) if _client else nullcontext(_NOOP)


def llm_config(name: str) -> dict:
    """LangChain config that records the model call as a generation under the current span."""
    if not _client:
        return {}
    return {"callbacks": [CallbackHandler(public_key=settings.langfuse_public_key)], "run_name": name}


def shutdown():
    if _client:
        _client.shutdown()  # flushes what is still queued
