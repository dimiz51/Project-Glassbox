"""The model the agent talks to: OpenAI when OPENAI_API_KEY and OPENAI_MODEL are set, otherwise Ollama.

Either way one call returns {"parsed": AgentAction | None, "raw": AIMessage}: the provider constrains
the reply to the AgentAction JSON schema.
"""

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.schemas.agent import AgentAction


def chat_model():
    if settings.provider == "openai":
        # no temperature: OpenAI's reasoning models only accept the default
        llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key)
    else:
        llm = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0,
            num_ctx=settings.ollama_num_ctx,
            repeat_penalty=settings.ollama_repeat_penalty,
            reasoning=settings.ollama_think,
        )
    return llm.with_structured_output(AgentAction, method="json_schema", include_raw=True)
