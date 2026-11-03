"""In-memory sessions: one sandbox browser context + LangChain chat history + event log each."""

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from langchain_core.messages import BaseMessage

from app.core.config import settings
from app.services.browser import BrowserSession


@dataclass
class Session:
    id: str
    browser: BrowserSession
    title: str = "New chat"
    created: float = field(default_factory=time.time)
    chat: list[BaseMessage] = field(default_factory=list)  # LangChain task/answer turns, for follow-ups
    events: list[dict] = field(default_factory=list)  # everything the UI needs, replayed on (re)connect
    subscribers: set[asyncio.Queue] = field(default_factory=set)  # open chat websockets
    inbox: asyncio.Queue = field(default_factory=asyncio.Queue)  # user messages sent mid-task
    task: asyncio.Task | None = None  # the running agent, if any

    @property
    def dir(self):
        d = settings.blob_dir / self.id
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def running(self) -> bool:
        return bool(self.task and not self.task.done())

    def publish(self, event: dict):
        self.events.append(event)
        for q in list(self.subscribers):
            q.put_nowait(event)


_sessions: dict[str, Session] = {}


async def create() -> Session:
    sid = uuid.uuid4().hex[:12]
    session = Session(id=sid, browser=await BrowserSession.create())
    _sessions[sid] = session
    return session


def get(sid: str) -> Session | None:
    return _sessions.get(sid)


def all() -> list[Session]:
    return sorted(_sessions.values(), key=lambda s: s.created, reverse=True)


async def close(sid: str):
    session = _sessions.pop(sid, None)
    if session:
        if session.task:
            session.task.cancel()
        await session.browser.close()


async def close_all():
    for sid in list(_sessions):
        await close(sid)
