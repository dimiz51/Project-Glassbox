"""The model the agent talks to: OpenAI or OpenRouter when their key + model are set, otherwise Ollama.

Whichever it is, one call returns {"parsed": AgentAction | None, "raw": AIMessage}: the provider constrains
the reply to the AgentAction JSON schema.
"""

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.schemas.agent import AgentAction


def chat_model():
    # no temperature for the cloud providers: reasoning models only accept the default
    if settings.provider == "openai":
        llm = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key)
    elif settings.provider == "openrouter":
        # OpenRouter speaks the OpenAI API: same client, different base URL
        llm = ChatOpenAI(
            model=settings.openrouter_model,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers={"X-OpenRouter-Title": "Project Glassbox"},  # optional: names the app in OpenRouter's activity view
        )
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
