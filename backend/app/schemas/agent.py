from typing import Literal

from pydantic import BaseModel, Field


class AgentAction(BaseModel):
    """One output of the model per turn. Ollama constrains generation to this schema.

    Browser actions are just one kind of output; `message` talks to the user, `done` ends the task.
    Field names follow Qwen3-VL's computer-use tool (`coordinate`, `text`) on its 0-1000 relative grid.
    """

    thought: str = Field(description="One sentence: what you see and why you do this.")
    action: Literal["navigate", "click", "type", "key", "scroll", "back", "wait", "message", "done"]
    # (x, y) on a 0-1000 grid over the screenshot: (0, 0) top-left, (1000, 1000) bottom-right
    coordinate: list[int] | None = Field(
        None, min_length=2, max_length=2, description="[x, y], each 0-1000. For click and type."
    )
    # URL (navigate), text to type (type), key name (key), up/down (scroll), or text for the user (message, done)
    text: str | None = Field(None, description="URL, text to type, key, up/down, or message to the user.")
