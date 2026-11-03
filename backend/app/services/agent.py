"""The agent: observe the sandbox browser -> ask the VLM for one output -> act -> repeat.

Read `BrowserAgent.run` top to bottom to see the whole loop; every step it calls:

    read_user_messages()  pick up anything the user typed while we were working
    observe()             screenshot + page state from the sandbox browser
    decide()              ask the model (LangChain + Ollama) for exactly one output
    respond()             output is `message` / `done`: talk to the user
    act()                 output is a browser action: run it in the sandbox browser

and when the task ends: give_up() if it ran out of steps, then remember() for follow-ups.
Every event goes to the UI (session.publish) and to session_blob/{id}/log.jsonl.
"""

import asyncio
import json
import time

from langchain_core.messages import AIMessage, HumanMessage
from langchain_ollama import ChatOllama

from app.core import errors
from app.core.config import settings
from app.core.errors import DomainError, ModelNotPulled, OllamaUnreachable
from app.schemas.agent import AgentAction
from app.services import prompts
from app.services.sessions import Session

TALK = ("message", "done")


class BrowserAgent:
    def __init__(self, session: Session, task: str):
        self.session = session
        self.browser = session.browser
        self.task = task
        self.llm = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0,
            num_ctx=settings.ollama_num_ctx,
            repeat_penalty=settings.ollama_repeat_penalty,
            reasoning=settings.ollama_think,
        ).with_structured_output(AgentAction, method="json_schema", include_raw=True)
        self.turns = [HumanMessage(task)]  # this task's conversation, kept for follow-up prompts
        self.history: list[str] = []  # one line per step, shown to the model
        self.step = 0

    # ---- the loop -------------------------------------------------------------

    async def run(self):
        self.emit("start", task=self.task, model=settings.ollama_model)
        try:
            for self.step in range(1, settings.max_steps + 1):
                self.read_user_messages()
                obs = await self.observe()
                action = await self.decide(obs)
                if action is None:
                    continue  # invalid output, already recorded; try again
                if action.action in TALK:
                    if self.respond(action):
                        return
                else:
                    await self.act(action)
            self.give_up()
        finally:
            self.remember()

    # ---- steps ----------------------------------------------------------------

    def read_user_messages(self):
        """Messages the user sent mid-task (steering) become part of the history and conversation."""
        while not self.session.inbox.empty():
            msg = self.session.inbox.get_nowait()
            self.history.append(f"{self.step}. USER SAID: {msg}")
            self.turns.append(HumanMessage(msg))

    async def observe(self) -> dict:
        """Screenshot (saved to session_blob) + URL, page text and clickable elements."""
        shot = self.session.dir / f"step_{int(time.time())}_{self.step:02d}.png"
        obs = await self.browser.observe(shot)
        self.emit("observe", url=obs["url"], title=obs["title"],
                  screenshot=f"/api/blob/{self.session.id}/{shot.name}")
        return obs

    async def decide(self, obs: dict) -> AgentAction | None:
        """One model call -> one structured output. Returns None if the output was unusable."""
        messages = [prompts.system_message(), *self.session.chat, prompts.state_message(self.task, self.history, obs)]
        t0 = time.time()
        try:
            action = self._parse(await self.llm.ainvoke(messages))
        except Exception as e:
            err = errors.from_model_error(e)
            if isinstance(err, (OllamaUnreachable, ModelNotPulled)):
                raise err from e  # no point retrying 30 times: stop the task and say why
            self.history.append(f"{self.step}. (invalid output: {err.out.detail})")
            self.emit_error(err)
            return None
        self.emit("action", thought=action.thought, action=action.action, label=self._describe(action),
                  coordinate=action.coordinate, seconds=round(time.time() - t0, 1))
        return action

    def respond(self, action: AgentAction) -> bool:
        """Talk to the user. Returns True when the task is finished."""
        text = action.text or action.thought
        repeated = any(isinstance(t, AIMessage) and t.content == text for t in self.turns)
        self.turns.append(AIMessage(text))
        if action.action == "done" or repeated:  # small models sometimes loop on `message`
            self.emit("answer", text=text, steps=self.step)
            return True
        self.history.append(f"{self.step}. you told the user: {text[:300]}")
        self.emit("message", text=text)
        return False

    async def act(self, action: AgentAction):
        """Run a browser action. Only action + outcome go into the history (feeding old thoughts
        back makes small models copy them and loop)."""
        try:
            note = await self._execute(action)
            self.history.append(f"{self.step}. {self._describe(action)}{f' → {note}' if note else ''}")
        except Exception as e:
            err = errors.BrowserActionFailed(self._describe(action), e)
            self.history.append(f"{self.step}. {self._describe(action)} FAILED: {err.out.detail}")
            self.emit_error(err)

    def give_up(self):
        text = f"I stopped after {settings.max_steps} steps without finishing. Try a more specific prompt."
        self.turns.append(AIMessage(text))
        self.emit("answer", text=text, steps=settings.max_steps)

    def remember(self):
        """Keep this task's conversation (LangChain messages) so follow-up prompts have context."""
        self.session.chat += self.turns

    # ---- plumbing -------------------------------------------------------------

    def emit(self, type: str, **data):
        event = {"type": type, "step": self.step, **data}
        with (self.session.dir / "log.jsonl").open("a") as log:
            log.write(json.dumps({"ts": time.time(), **event}) + "\n")
        self.session.publish(event)

    def emit_error(self, err: DomainError, fatal: bool = False):
        self.emit("error", fatal=fatal, error=err.out.model_dump(mode="json"))

    async def _execute(self, a: AgentAction) -> str | None:
        """Dispatch to the sandbox browser; returns an optional note on what happened."""
        b = self.browser
        match a.action:
            case "navigate":
                await b.navigate(a.text or "")
            case "click":
                return await b.click(a.coordinate)
            case "type":
                await b.type(a.coordinate, a.text or "")
            case "key":
                await b.press(a.text or "Enter")
            case "scroll":
                return await b.scroll("up" if (a.text or "").lower() == "up" else "down")
            case "back":
                await b.back()
            case "wait":
                await b.page.wait_for_timeout(2000)

    @staticmethod
    def _parse(result: dict) -> AgentAction:
        if result.get("parsed"):
            return result["parsed"]
        raw = getattr(result.get("raw"), "content", "") or ""
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            return AgentAction.model_validate(json.loads(raw[start : end + 1]))
        raise ValueError(f"model did not return a valid action: {raw[:200]!r}")

    @staticmethod
    def _describe(a: AgentAction) -> str:
        at = f"[{a.coordinate[0]}, {a.coordinate[1]}]" if a.coordinate else "[?]"
        match a.action:
            case "navigate":
                return f"navigate → {a.text}"
            case "click":
                return f"click {at}"
            case "type":  # no coordinate = typed into the field that already had focus
                return f"type {at} \"{a.text}\"" if a.coordinate else f"type \"{a.text}\""
            case "key":
                return f"key {a.text}"
            case "scroll":
                return f"scroll {a.text or 'down'}"
            case _:
                return a.action


def start(session: Session, task: str):
    """Runs a BrowserAgent in the background; its events reach the UI through session.publish."""

    async def drive():
        try:
            await BrowserAgent(session, task).run()
        except asyncio.CancelledError:
            session.publish({"type": "stopped"})
        except DomainError as e:
            session.publish({"type": "error", "fatal": True, "error": e.out.model_dump(mode="json")})
        except Exception as e:
            session.publish({"type": "error", "fatal": True, "error": errors.AgentCrashed(e).out.model_dump(mode="json")})

    session.task = asyncio.create_task(drive())
