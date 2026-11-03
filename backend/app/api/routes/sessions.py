import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.errors import error_responses
from app.core import errors
from app.schemas.errors import ErrorCode
from app.schemas.api import OkOut, SessionOut
from app.services import agent, sessions

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _out(s: sessions.Session) -> SessionOut:
    return SessionOut(session_id=s.id, title=s.title, created=s.created, running=s.running)


@router.get("", response_model=list[SessionOut], summary="List sessions")
async def list_sessions():
    """All sessions, newest first, with their title and whether an agent is running."""
    return [_out(s) for s in sessions.all()]


@router.post("", response_model=SessionOut, summary="Create a session",
             responses=error_responses(ErrorCode.BROWSER_START_FAILED))
async def create_session():
    """Starts a fresh sandbox browser context with an empty profile."""
    try:
        return _out(await sessions.create())
    except Exception as e:
        raise errors.BrowserStartFailed(e) from e


@router.delete("/{sid}", response_model=OkOut, summary="Delete a session",
               responses=error_responses(ErrorCode.SESSION_NOT_FOUND, ErrorCode.INVALID_REQUEST))
async def delete_session(sid: str):
    """Stops its agent and closes its sandbox browser. Screenshots stay in session_blob/."""
    if not sessions.get(sid):
        raise errors.SessionNotFound(sid)
    await sessions.close(sid)
    return OkOut()


@router.websocket("/{sid}/chat")
async def chat(ws: WebSocket, sid: str):
    """Two-way chat with the agent. The agent keeps running if the socket closes.

    client -> server: {"type": "prompt", "text": "..."}  starts a task, or steers the running one
                      {"type": "stop"}                   cancels the running task
    server -> client: every past event of the session (replay), then live ones:
                      user | start | observe | action | message | error | answer | stopped
    """
    session = sessions.get(sid)
    await ws.accept()
    if not session:
        err = errors.SessionNotFound(sid).out.model_dump(mode="json")
        await ws.send_json({"type": "error", "fatal": True, "error": err})
        await ws.close(code=4404)
        return

    queue: asyncio.Queue = asyncio.Queue()
    for event in session.events:
        queue.put_nowait(event)
    session.subscribers.add(queue)

    async def pump():
        while True:
            await ws.send_json(await queue.get())

    sender = asyncio.create_task(pump())
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "prompt" and msg.get("text", "").strip():
                text = msg["text"].strip()
                session.publish({"type": "user", "text": text})
                if session.running:
                    session.inbox.put_nowait(text)  # picked up at the agent's next step
                else:
                    if session.title == "New chat":
                        session.title = text[:60]
                    agent.start(session, text)
            elif msg.get("type") == "stop" and session.running:
                session.task.cancel()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        sender.cancel()
        session.subscribers.discard(queue)


@router.websocket("/{sid}/live")
async def live(ws: WebSocket, sid: str):
    """Read-only live view of the sandbox browser: {"img": base64 jpeg, "url": ...} frames.
    Only the agent controls the browser; anything the client sends here is ignored."""
    session = sessions.get(sid)
    await ws.accept()
    if not session:
        await ws.close(code=4404)
        return
    browser = session.browser
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)  # only ever the latest frame
    if browser.last_frame:
        queue.put_nowait(browser.last_frame)
    browser.viewers.add(queue)

    async def pump():
        while True:
            await ws.send_text(await queue.get())

    sender = asyncio.create_task(pump())
    try:
        while True:
            await ws.receive_text()  # only to notice the client leaving
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        sender.cancel()
        browser.viewers.discard(queue)
