# Project Glassbox

You give a prompt. A **local vision model** (Ollama) drives a **sandboxed Chromium** until it can answer. You watch its browser live next to the chat and can steer the agent with chat messages.

![Glassbox answering "how tall is the Eiffel Tower and when was it built" by browsing Wikipedia (qwen3.5:9b, 5 steps, sped up 4×)](readme-images/demo.gif)

```
 your browser: Svelte UI (:3000)              backend container: FastAPI (:8000)
┌──────────────────────────────┐             ┌─────────────────────────────────────────┐
│ chat panel                   │◄─ ws/chat ─►│ BrowserAgent loop ── LangChain ──►  Ollama (your machine)
│ live browser view (read-only)│◄─ ws/live ──│ sandbox Chromium (Playwright, Xvfb)     │
└──────────────────────────────┘  frames     │ screenshots → ./session_blob/{id}/      │
                                             └─────────────────────────────────────────┘
```

## How it works

The loop is `BrowserAgent.run` in [backend/app/services/agent.py](backend/app/services/agent.py). Read it top to bottom. Each step calls:

| Method | Role |
|---|---|
| `read_user_messages()` | pick up anything you typed while the agent was working (steering) |
| `observe()` | screenshot of the sandbox browser (saved to `session_blob/{id}/`), plus the URL, the page text, and clickable elements with their centre on a **0–1000 grid** |
| `decide()` | one LangChain `ChatOllama` call. Ollama constrains the reply to one JSON object ([schema](backend/app/schemas/agent.py)) |
| `respond()` | the output is `message` (talk to you, keep working) or `done` (final answer) |
| `act()` | the output is a browser action, run with Playwright |

When the task ends, `give_up()` runs if the agent hit `MAX_STEPS`, then `remember()` keeps the conversation (LangChain messages) for follow-up prompts. What the model reads (system prompt and per-step state) is in [prompts.py](backend/app/services/prompts.py).

```json
{"thought": "Search box is at the top", "action": "type", "coordinate": [478, 615], "text": "Chicago O'Hare"}
```

`action` is one of:
- a browser action: `navigate`, `click`, `type`, `key`, `scroll`, `back`, `wait`
- `message`: talk to you and keep working
- `done`: give the final answer

Notes on the design:
- **Coordinates:** Qwen-VL models point on a relative 0–1000 grid ([Qwen3-VL cookbook](https://github.com/QwenLM/Qwen3-VL/blob/main/cookbooks/2d_grounding.ipynb)). `coordinate`/`text` match Qwen's computer-use tool. The backend scales `coordinate` to the 1280×800 viewport, so clicks happen on the real page and a cursor shows each click in the live view.
- **Feedback and loop guards:** after a click, the model is told what got focus (e.g. `focused input "Search Wikipedia"`). Its past thoughts are not fed back, because small models copy them and loop. Repeating the same action triggers a warning to try something different.
- **Sessions:** each chat in the sidebar has its own sandbox browser and keeps running when you switch away. Every event is logged per session and replayed when you open it again.
- **Sandbox, not your Chrome:** the agent drives its own Chromium inside the backend container. It has an empty profile: none of your cookies, logins, passwords or extensions. Each session gets its own isolated browser context, which is thrown away when you delete the session or stop the stack. The container can reach the internet, Ollama on your machine, and `./session_blob`, nothing else.
- **Live view is read-only:** your Chrome only loads the Glassbox page. The sandbox streams video frames of its own browser (Chrome's screencast) one way to the UI. Websites never load in your browser, and the live view and address bar take no input. Only the agent controls the sandbox browser. Each step's screenshot is also pushed to the live view before the model decides, so the live view always ends on the page the answer came from.
- **No handoffs in v0:** the agent doesn't log in or buy anything, it only researches and reports.

```
backend/app/
  main.py               FastAPI app, mounts /api/blob (screenshots)
  core/config.py        settings (.env)
  api/routes/           health, sessions (list/create/delete, ws /chat, ws /live)
  schemas/              API + agent output models
  services/agent.py     BrowserAgent: the loop
  services/prompts.py   what the model reads
  services/browser.py   sandbox Chromium: observe, act, live screencast
  services/sessions.py  in-memory sessions + event log
frontend/src/
  App.svelte            layout + websockets
  lib/                  Sidebar, Chat, BrowserPanel, reduce.js (events → UI state)
```

## Demo, step by step

**Prerequisites:** Docker, and [Ollama](https://ollama.com) installed on your machine.

1. **Start Ollama and pull a vision model**
   ```bash
   ollama serve                 # skip if the Ollama app is already running
   ollama pull qwen3.5:9b       # ~7.6 GB: newest Qwen with a ~9B size (vision + tools)
   ```
2. **Configure (optional)**
   ```bash
   cp .env.example .env         # change the model, steps, etc.
   ```
3. **Start everything**
   ```bash
   docker compose up --build
   ```
4. **Open http://localhost:3000.** The model chip at top right turns green once Ollama is reachable and the model is pulled.
5. **Send a prompt**, or click a suggestion, for example:
   > Open skyscanner.se, find one-way flights from Stockholm to Chicago on 25 November and tell me my options below 10,000 SEK
6. **Watch it:**
   - The right-hand panel shows the sandbox browser **live**, with the agent's cursor moving to each click.
   - The chat shows each step: the action, the model's reasoning, and how long it took.
   - Click a step's number, or a thumbnail, to see **Agent's view**: the exact screenshot the model saw and where it pointed.
7. **Steer it** while it runs ("only direct flights", "try Google Flights instead"), or press **Stop**.
8. **Ask a follow-up** after it answers ("which one is fastest?"). It keeps the same browser and conversation.
9. **New chat** in the sidebar starts another session with its own browser. Switch between them freely; running agents keep going. Screenshots and a `log.jsonl` of every event stay in `./session_blob/{session_id}/` (git-ignored).

### Run without Docker (dev)

```bash
cd backend && uv sync && uv run playwright install chromium
uv run uvicorn app.main:app --reload --port 8000   # HEADLESS=false in .env shows the sandbox window
cd frontend && npm install && npm run dev          # http://localhost:5173 (proxies /api to :8000)
```

## API & errors

- **Swagger UI:** http://localhost:3000/api/docs (also on :8000). There's also ReDoc at `/api/redoc` and the raw spec at `/api/openapi.json`. The WebSocket protocols (`/chat`, `/live`) are described in the `sessions` section, since OpenAPI can't model WebSockets.
- **Typed errors:** every error has the same shape, both as HTTP responses and as agent `error` events on the WebSocket:
  ```json
  {"code": "model_not_pulled", "message": "The model qwen3.5:9b isn't downloaded yet.",
   "hint": "Run `ollama pull qwen3.5:9b`, or set OLLAMA_MODEL in .env to a model you have.", "detail": null}
  ```
  The UI shows `message` and `hint`. `detail` is the technical cause, shown on hover.

| Layer | File | Role |
|---|---|---|
| Contract | [schemas/errors.py](backend/app/schemas/errors.py) | `ErrorCode` + `ErrorOut`, the wire shape |
| Domain | [core/errors.py](backend/app/core/errors.py) | one exception class per error (`OllamaUnreachable`, `SessionNotFound`, …), no HTTP |
| HTTP translator | [api/errors.py](backend/app/api/errors.py) | maps each `ErrorCode` to a status code (404, 422, 502, 503, …). Validation errors, unknown routes and crashes also become `ErrorOut` |
| UI | [frontend/src/lib/api.js](frontend/src/lib/api.js) | typed client, plus browser-only codes (`backend_unreachable`, `connection_lost`) |

If Ollama is down or the model isn't pulled, a running task stops right away with that error instead of retrying.

## Models

| `OLLAMA_MODEL` | Notes |
|---|---|
| `qwen3.5:9b` (default) | Good balance. Around 10–25 s per step on an M-series Mac |

Set `OLLAMA_THINK=true` to turn on thinking mode: the model plans better but each step is much slower. `OLLAMA_REPEAT_PENALTY` (default 1.1) discourages repeated tokens within one reply. If the agent repeats the same `message`, the backend ends the task.
