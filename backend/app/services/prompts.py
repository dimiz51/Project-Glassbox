"""Everything the model reads: the system prompt and the step-by-step conversation.

Each step adds a screenshot (user turn) and the model's action (assistant turn). Only the latest steps
are sent, and only the newest HISTORY_IMAGES screenshots (default 3) carry the image. HISTORY_IMAGES=0
is text-only mode: no images at all, the model works from the element list (for text-only models).
"""

import base64
from datetime import date

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.core.config import settings
from app.schemas.agent import AgentAction

SYSTEM_PROMPT = """You are a web agent controlling a real Chromium browser to complete the user's task.
Today is {today}.

{view}
Positions are [x, y] in relative coordinates 0-1000 ([0, 0] = top-left, [1000, 1000] = bottom-right
of the screen), whatever its size in pixels.
Reply with exactly ONE output as JSON:

Browser actions:
- navigate: open the URL in `text` (do this first if the page is blank; prefer direct URLs)
- click: click at `coordinate` [x, y]
- type: click the field at `coordinate` [x, y] and replace its content with `text` (no need to click it first)
- key: press the key in `text` (Enter, Escape, Tab, ArrowDown...), e.g. Enter after typing a search
- scroll: `text` is "down" or "up" plus how many screens ("down 3", "up 0.5"; just "down" = most of a
  screen), or "top" / "bottom". Use the visible % of the page to judge how far to go.
- back: go back in history
- wait: wait for the page to load

Talking to the user:
- message: send `text` to the user and KEEP WORKING (progress or partial findings while the task is unfinished)
- done: finish the task; `text` is the final answer (markdown; concrete findings like prices, times, links)
As soon as you can answer the task, use done (not message).

Rules:
- Click what is in the element list (or visible on screen), taking the coordinate from the list
  when the target is listed. Text that looks like a heading may be a link: check the list.
- If what you need is not on screen, scroll to find it (site links like Careers or Contact are often
  in the menu or the footer).
- Dismiss cookie banners / popups first if they cover the page.
- Autocomplete fields: type, then click the right suggestion in the next step.
- Never repeat the same action on an unchanged page; if it didn't work, try something different.
- If something fails twice, try another way (somewhere else on screen, a direct URL with query params, another website).
- On a CAPTCHA or login wall, try an alternative site; if impossible, finish with done and explain.
- Never buy, book, log in or submit personal data. Research and report.
- If the user messages you mid-task, follow their instruction; answer questions with `message`.
- Use `message` sparingly; never repeat a message you already sent.
"""


VISION_VIEW = """Every step you get a screenshot of the browser, the current URL and the tab title, which part of the
page is visible (in % of the page height, so you know if there is more below), and a list of the
interactive elements on screen right now (links, buttons, inputs...) with their centre. Your previous
steps are in the conversation, each action followed by the screenshot it led to (only the latest few
screenshots are attached). The last screenshot is the screen right now; the ones before it show what
your recent actions did."""

TEXT_ONLY_VIEW = """You cannot see the screen. Every step you get the current URL and the tab title, which part of the
page is visible (in % of the page height, so you know if there is more below), and a list of the
interactive elements on screen right now (links, buttons, inputs...) with their label and centre. That
list is all you know about the page: pick targets from it, and scroll when what you need isn't listed.
Your previous steps are in the conversation."""


def text_only() -> bool:
    return settings.history_images == 0


def system_message() -> SystemMessage:
    view = TEXT_ONLY_VIEW if text_only() else VISION_VIEW
    return SystemMessage(content=SYSTEM_PROMPT.format(today=date.today().strftime("%A %d %B %Y"), view=view))


def observation(step: int, obs: dict) -> HumanMessage:
    """One step's view of the browser. It stays in the conversation, so later steps can see it."""
    b64 = base64.b64encode(obs["png"]).decode()
    return HumanMessage(content=[
        {"type": "text", "text": f"Step {step}: {obs['url']} \"{obs['title']}\""},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},  # OpenAI + Ollama format
    ])


def action(a: AgentAction) -> AIMessage:
    """The model's output without its thought: small models copy old thoughts and loop."""
    return AIMessage(a.model_dump_json(exclude={"thought"}, exclude_none=True))


def conversation(task: str, history: list[str], steps: list[BaseMessage], obs: dict) -> list[BaseMessage]:
    """The user's task (always first), the latest steps (images only on the newest HISTORY_IMAGES),
    then the state of the browser now: steps so far, which part of the page is visible, and the
    elements on the current screen."""
    recent = steps[-settings.history_messages:]
    while recent and isinstance(recent[0], AIMessage):  # start on a screenshot, not an orphan action
        recent = recent[1:]
    shots = [i for i, m in enumerate(recent) if isinstance(m.content, list)]
    old = set(shots[: -settings.history_images] if settings.history_images else shots)
    recent = [_without_image(m) if i in old else m for i, m in enumerate(recent)]
    now = (
        "BROWSER STATE (not a message from the user)\n\n"
        + "Your steps so far:\n" + ("\n".join(history[-15:]) or "(none yet)") + "\n\n"
        + loop_warning(history)
        + format_scroll(obs["scroll"])
        + f"Interactive elements on the current screen [x, y]:\n{format_elements(obs['elements'])}\n\n"
        + ("That list is the screen right now." if text_only() else "The last screenshot above is the screen right now.")
        + " What is your next output?"
    )
    return [HumanMessage(task), *recent, HumanMessage(now)]


def format_scroll(s: dict | None) -> str:
    """Which part of the page is on screen, in % of the page height (never pixels)."""
    if not s:
        return ""
    top, bottom = round(s["top"] * 100), round(s["bottom"] * 100)
    where = "end of page" if bottom >= 100 else "more below"
    return f"Visible: {top}–{bottom}% of the page (page is {s['screens']:.1f} screens tall, {where})\n\n"


def format_elements(elements: list[dict]) -> str:
    lines = []
    for el in elements:
        kind = el["role"] or el["tag"] + (f"[{el['type']}]" if el["type"] else "")
        lines.append(f"[{el['x']}, {el['y']}] {kind} \"{el['label']}\"")
    return "\n".join(lines) or "(none visible)"


def _without_image(m: HumanMessage) -> HumanMessage:
    return HumanMessage(content=[*(c for c in m.content if c["type"] == "text"),
                                 {"type": "text", "text": "(screenshot omitted)"}])


def loop_warning(history: list[str]) -> str:
    """Repetition guard: small models can get stuck doing the same thing on an unchanged page."""
    actions = [h.split(". ", 1)[-1].split(" → ")[0] for h in history]
    repeats = 0
    while repeats < len(actions) and actions[-1 - repeats] == actions[-1]:
        repeats += 1
    if repeats < 2:
        return ""
    return (f"WARNING: you did `{actions[-1]}` {repeats} times in a row and it is not working. "
            "Do something DIFFERENT now (e.g. `type` into the field, `key` Enter, somewhere else on screen, "
            "or navigate to a URL directly).\n\n")
