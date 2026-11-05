# Project Glassbox

You give a prompt. A **vision model** (local with Ollama, or OpenAI / OpenRouter) drives a **sandboxed Chromium** until it can answer. You watch its browser live next to the chat and can steer the agent with chat messages.

![Glassbox answering "how tall is the Eiffel Tower and when was it built" by browsing Wikipedia (qwen3.5:9b, 5 steps, sped up 4×)](readme-images/demo.gif)

```
 your browser: Svelte UI (:3000)              backend container: FastAPI (:8000)
┌──────────────────────────────┐             ┌─────────────────────────────────────────┐
│ chat panel                   │◄─ ws/chat ─►│ BrowserAgent loop ── LangChain ──►  Ollama (your machine), OpenAI or OpenRouter
│ live browser view (read-only)│◄─ ws/live ──│ sandbox Chromium (Playwright, Xvfb)     │
└──────────────────────────────┘  frames     │ screenshots → ./session_blob/{id}/      │
                                             └─────────────────────────────────────────┘
```

## How it works

The loop is `BrowserAgent.run` in [backend/app/services/agent.py](backend/app/services/agent.py). Read it top to bottom. Each step calls:

| Method | Role |
|---|---|
| `read_user_messages()` | pick up anything you typed while the agent was working (steering) |
| `observe()` | waits for the page to load and settle, then takes a screenshot (saved to `session_blob/{id}/`) and lists the interactive elements on screen with their centre on a **0–1000 grid**, plus the URL, tab title and which part of the page is visible (in % of its height) |
| `decide()` | one LangChain model call ([llm.py](backend/app/services/llm.py): Ollama, OpenAI or OpenRouter). It gets your task, the last `HISTORY_MESSAGES` messages of steps and actions (default 10; only the newest `HISTORY_IMAGES` screenshots are sent as images, default 3), and the current browser state. The provider constrains the reply to one JSON object ([schema](backend/app/schemas/agent.py)) |
| `respond()` | the output is `message` (talk to you, keep working) or `done` (final answer) |
| `act()` | the output is a browser action, run with Playwright |

When the task ends, `give_up()` runs if the agent hit `MAX_STEPS`, then `remember()` keeps the conversation (LangChain messages) for follow-up prompts. What the model reads (system prompt and per-step state) is in [prompts.py](backend/app/services/prompts.py).

```json
{"thought": "Search box is at the top", "action": "type", "coordinate": [478, 615], "text": "Chicago O'Hare"}
```

`action` is one of:
- a browser action: `navigate`, `click`, `type`, `key`, `scroll`, `back`, `wait`. For `scroll`, the model picks the distance: `down`, `down 3` (screens), `up 0.5`, `top`, `bottom`
- `message`: talk to you and keep working
- `done`: give the final answer

### Notes

- **Screenshots + elements, no page text.** The model sees the latest screenshots and a list of the interactive elements on screen now (kind, label, position). It never gets the page's text, so it can only read what is on screen.
- **Page position.** Each step also says which part of the page is visible, e.g. `Visible: 0–3% of the page (page is 39.1 screens tall, more below)`, so the model knows how far to scroll.
- **Waits before looking.** Each screenshot waits for the page to load and its requests to settle (capped), so late content like cookie banners is on screen.
- **Coordinates** are on Qwen-VL's 0–1000 grid ([cookbook](https://github.com/QwenLM/Qwen3-VL/blob/main/cookbooks/2d_grounding.ipynb)), scaled to the 1280×800 viewport.
- **The live view is screenshots, not a browser.** Chromium runs in the backend container and streams JPEG frames (CDP screencast) to an `<img>`. Websites never load in your browser, and the view takes no input.
- **Sandboxed.** Each session has its own empty, throwaway browser context: none of your cookies, logins or extensions.
- **Loop guards.** Past thoughts aren't fed back, since small models copy them. Repeating an action triggers a warning.
- **Research only.** It never logs in, buys or submits anything.

```
backend/app/
  main.py               FastAPI app, mounts /api/blob (screenshots)
  core/config.py        settings (.env)
  api/routes/           health, sessions (list/create/delete, ws /chat, ws /live)
  schemas/              API + agent output models
  services/agent.py     BrowserAgent: the loop
  services/llm.py       the model: OpenAI or OpenRouter if configured, otherwise Ollama
  services/prompts.py   what the model reads
  services/browser.py   sandbox Chromium: observe, act, live screencast
  services/sessions.py  in-memory sessions + event log
  services/tracing.py   optional Langfuse tracing
frontend/src/
  App.svelte            layout + websockets
  lib/                  Sidebar, Chat, BrowserPanel, reduce.js (events → UI state)
```

## Demo, step by step

**Prerequisites:** Docker, and [Ollama](https://ollama.com) installed on your machine (or an OpenAI or OpenRouter key, see [Models](#models)).

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
4. **Open http://localhost:3000.** The model chip in the sidebar turns green once the model can run (Ollama reachable and the model pulled, or OpenAI / OpenRouter accepting the key and model).
5. **Send a prompt**, or click a suggestion, for example:
   > Open skyscanner.se, find one-way flights from Stockholm to Chicago on 25 November and tell me my options below 10,000 SEK
6. **Watch it:**
   - The right-hand panel shows the sandbox browser **live**, with the agent's cursor moving to each click.
   - The chat shows each step: the action, the model's reasoning, and how long it took.
   - Click a step's number, or switch to **Agent view**, to see the exact screenshot the model saw and where it pointed. Agent view also has a strip of every step to browse.
7. **Steer it** while it runs ("only direct flights", "try Google Flights instead"), or press **Stop**.
8. **Ask a follow-up** after it answers ("which one is fastest?"). It keeps the same browser and conversation.
9. **New chat** in the sidebar starts another session with its own browser. Switch between them freely; running agents keep going. Screenshots and a `log.jsonl` of every event stay in `./session_blob/{session_id}/` (git-ignored).

### Tracing with Langfuse (optional)

Set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL` in `.env` (see [.env.example](.env.example)) and restart. Each task becomes one trace, grouped by chat session:

```
task                prompt in, final answer out
  step 1
    decide          the model call: exact messages + screenshots sent, raw reply, latency
    click           the browser action and its outcome (ERROR level if it failed)
  step 2 ...
```

With the keys unset, tracing is off and no traces leave your machine.

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

If the model can't run (Ollama down, model not pulled, or OpenAI / OpenRouter rejecting the key or model: `model_unavailable`), a running task stops right away with that error instead of retrying.

## Models

The agent runs on **Ollama** (local) by default. Set both `OPENAI_API_KEY` and `OPENAI_MODEL` in `.env` to use **OpenAI** instead, with any OpenAI vision model that supports structured outputs. Remove either to go back to Ollama.

**OpenRouter** gives you any model (Qwen, Gemini, Claude, GPT, …) through one key: set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` to an OpenRouter model id, e.g. `qwen/qwen3-vl-32b-instruct`. It speaks the OpenAI API, so it's the same client with a different base URL. Pick a model that takes images and supports structured outputs ([filtered list](https://openrouter.ai/models?modality=image&supported_parameters=structured_outputs)). If both pairs are set, OpenAI wins.

With a cloud provider, the screenshots of the sites the agent visits are sent to it. Everything else stays the same (prompt, screenshots, element list), so runs are comparable. Langfuse tags each trace with the provider and model, so you can filter and compare runs of the same task.

| `OLLAMA_MODEL` | Notes |
|---|---|
| `qwen3.5:9b` (default) | Good balance. Around 10–25 s per step on an M-series Mac |

Set `OLLAMA_THINK=true` to turn on thinking mode: the model plans better but each step is much slower. `OLLAMA_REPEAT_PENALTY` (default 1.1) discourages repeated tokens within one reply. If the agent repeats the same `message`, the backend ends the task.
