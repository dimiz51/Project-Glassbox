"""Everything the model reads: the system prompt and the per-step state message."""

import base64
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings

SYSTEM_PROMPT = """You are a web agent controlling a real Chromium browser to complete the user's task.
Today is {today}.

Every turn you get: the current URL, a screenshot, a list of interactive elements with their centre
as [x, y] in relative coordinates 0-1000 ([0, 0] = top-left, [1000, 1000] = bottom-right of the
screenshot), and the visible page text. Reply with exactly ONE output as JSON:

Browser actions:
- navigate: open the URL in `text` (do this first if the page is blank; prefer direct URLs)
- click: click at `coordinate` [x, y]
- type: click the field at `coordinate` [x, y] and replace its content with `text` (no need to click it first)
- key: press the key in `text` (Enter, Escape, Tab, ArrowDown...), e.g. Enter after typing a search
- scroll: scroll `text` "down" or "up" by most of a screen
- back: go back in history
- wait: wait for the page to load

Talking to the user:
- message: send `text` to the user and KEEP WORKING (progress or partial findings while the task is unfinished)
- done: finish the task; `text` is the final answer (markdown; concrete findings like prices, times, links)
As soon as you can answer the task, use done (not message).

Rules:
- Take the coordinate from the element list when the target is listed; otherwise point at it in the screenshot.
- Dismiss cookie banners / popups first if they cover the page.
- Autocomplete fields: type, then click the right suggestion in the next step.
- Never repeat the same action on an unchanged page; if it didn't work, try something different.
- If something fails twice, try another way (other element, a direct URL with query params, another website).
- On a CAPTCHA or login wall, try an alternative site; if impossible, finish with done and explain.
- Never buy, book, log in or submit personal data. Research and report.
- If the user messages you mid-task, follow their instruction; answer questions with `message`.
- Use `message` sparingly; never repeat a message you already sent.
"""


def system_message() -> SystemMessage:
    return SystemMessage(content=SYSTEM_PROMPT.format(today=date.today().strftime("%A %d %B %Y")))


def state_message(task: str, history: list[str], obs: dict) -> HumanMessage:
    """What the model sees this step: task, steps so far, page state, and the screenshot."""
    s = obs["scroll"]
    text = (
        f"TASK: {task}\n\n"
        + "Steps so far:\n" + ("\n".join(history[-15:]) or "(none yet)") + "\n\n"
        + loop_warning(history)
        + f"Current URL: {obs['url']}\nTitle: {obs['title']}\n"
        + f"Viewing {s['y']}–{s['y'] + s['vh']}px of {s['h']}px page height\n\n"
        + f"Interactive elements [x, y]:\n{format_elements(obs['elements'])}\n\n"
        + f"Page text (truncated):\n{obs['text']}\n\n"
        + "What is your next output?"
    )
    content: list[dict] = [{"type": "text", "text": text}]
    if settings.use_vision:
        b64 = base64.b64encode(obs["png"]).decode()
        content.append({"type": "image_url", "image_url": f"data:image/png;base64,{b64}"})
    return HumanMessage(content=content)


def format_elements(elements: list[dict]) -> str:
    lines = []
    for el in elements:
        kind = el["role"] or el["tag"] + (f"[{el['type']}]" if el["type"] else "")
        lines.append(f"[{el['x']}, {el['y']}] {kind} \"{el['label']}\"")
    return "\n".join(lines) or "(none visible)"


def loop_warning(history: list[str]) -> str:
    """Repetition guard: small models can get stuck doing the same thing on an unchanged page."""
    actions = [h.split(". ", 1)[-1].split(" → ")[0] for h in history]
    repeats = 0
    while repeats < len(actions) and actions[-1 - repeats] == actions[-1]:
        repeats += 1
    if repeats < 2:
        return ""
    return (f"WARNING: you did `{actions[-1]}` {repeats} times in a row and it is not working. "
            "Do something DIFFERENT now (e.g. `type` into the field, `key` Enter, another element, "
            "or navigate to a search URL directly).\n\n")
