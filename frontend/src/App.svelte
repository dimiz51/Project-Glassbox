<script>
  import { onMount } from 'svelte'
  import Sidebar from './lib/Sidebar.svelte'
  import Chat from './lib/Chat.svelte'
  import BrowserPanel from './lib/BrowserPanel.svelte'
  import Icon from './lib/Icon.svelte'
  import { reduce } from './lib/reduce.js'
  import { api, toError, CLIENT_ERRORS } from './lib/api.js'

  let health = $state(null) // { ok, model, ollama_url, error }
  let sessions = $state([])
  let activeId = $state(null)
  let events = $state.raw([]) // event log of the active session (replayed by the backend)
  let frame = $state(null) // latest live JPEG of the active session's browser
  let liveUrl = $state('') // URL of the live page, sent with every frame
  let view = $state('live')
  let picked = $state(null)
  let sidebarOpen = $state(false)
  let connected = $state(false)
  let notice = $state(null) // typed error shown above the chat until dismissed or resolved

  let liveWs, chatWs

  const ui = $derived(reduce(events))
  const CONNECTION_CODES = ['backend_unreachable', 'connection_lost']

  const wsUrl = (path) => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}${path}`

  async function checkHealth() {
    try {
      health = await api('/health')
      if (CONNECTION_CODES.includes(notice?.code)) {
        notice = null // server is back: reconnect
        if (!connected) boot()
      }
    } catch (e) {
      health = { ok: false, model: null, error: toError(e) }
    }
  }

  async function loadSessions() {
    try {
      sessions = await api('/sessions')
    } catch (e) {
      notice = toError(e)
    }
  }

  function open(sid) {
    liveWs?.close()
    chatWs?.close()
    activeId = sid
    events = []
    frame = null
    liveUrl = ''
    view = 'live'
    picked = null
    connected = false
    sidebarOpen = false
    history.replaceState(null, '', `#${sid}`)

    liveWs = new WebSocket(wsUrl(`/api/sessions/${sid}/live`))
    liveWs.onmessage = (e) => {
      if (sid !== activeId) return
      const msg = JSON.parse(e.data)
      frame = `data:image/jpeg;base64,${msg.img}`
      liveUrl = msg.url
    }

    chatWs = new WebSocket(wsUrl(`/api/sessions/${sid}/chat`))
    chatWs.onopen = () => (connected = true)
    chatWs.onmessage = (e) => {
      if (sid !== activeId) return
      const ev = JSON.parse(e.data)
      if (ev.type === 'error' && ev.error?.code === 'session_not_found') {
        notice = ev.error
        return
      }
      events = [...events, ev]
      if (ev.type === 'observe') picked = null
      if (['user', 'answer', 'stopped'].includes(ev.type)) loadSessions() // titles + running dots
    }
    chatWs.onclose = (e) => {
      if (sid !== activeId) return // closed on purpose: we switched sessions
      connected = false
      if (e.code !== 4404) notice = CLIENT_ERRORS.connection_lost
      checkHealth() // update the model status right away instead of on the next poll
    }
  }

  async function create() {
    try {
      const s = await api('/sessions', { method: 'POST' })
      await loadSessions()
      open(s.session_id)
      notice = null
    } catch (e) {
      notice = toError(e)
    }
  }

  async function remove(sid) {
    try {
      await api(`/sessions/${sid}`, { method: 'DELETE' })
    } catch (e) {
      if (toError(e).code !== 'session_not_found') return (notice = toError(e)) // already gone is fine
    }
    await loadSessions()
    if (sid === activeId) sessions.length ? open(sessions[0].session_id) : create()
  }

  async function boot() {
    await loadSessions()
    if (notice) return
    const fromHash = location.hash.slice(1)
    const existing = sessions.find((s) => s.session_id === fromHash) ?? sessions.find((s) => s.title === 'New chat')
    existing ? open(existing.session_id) : create()
  }

  const send = (text) => chatWs?.send(JSON.stringify({ type: 'prompt', text }))
  const stop = () => chatWs?.send(JSON.stringify({ type: 'stop' }))

  function pickStep(src) {
    const i = ui.shots.findIndex((s) => s.src === src)
    if (i >= 0) {
      picked = i
      view = 'agent'
    }
  }

  onMount(() => {
    checkHealth()
    boot()
    const t1 = setInterval(checkHealth, 5000)
    const t2 = setInterval(() => connected && loadSessions(), 5000)
    return () => {
      clearInterval(t1)
      clearInterval(t2)
    }
  })
</script>

<div class="app">
  <Sidebar {sessions} {activeId} {health} bind:open={sidebarOpen} onselect={open} oncreate={create} ondelete={remove} />
  {#if sidebarOpen}<button class="scrim" onclick={() => (sidebarOpen = false)} aria-label="Close sidebar"></button>{/if}

  <main class="main">
    <header class="top">
      <button class="icon-btn" onclick={() => (sidebarOpen = true)} aria-label="Open sessions"><Icon name="sidebar" /></button>
      <span>{sessions.find((s) => s.session_id === activeId)?.title ?? 'Project Glassbox'}</span>
      <button class="icon-btn" onclick={create} aria-label="New chat"><Icon name="edit" /></button>
    </header>
    <div class="chat-col">
      <Chat messages={ui.messages} running={ui.running} ready={connected} {notice} ondismiss={() => (notice = null)} onsend={send} onstop={stop} onpickstep={pickStep} />
    </div>
    <div class="browser-col">
      <BrowserPanel {frame} url={liveUrl || ui.url} shots={ui.shots} point={ui.point} running={ui.running} bind:view bind:picked />
    </div>
  </main>
</div>

<style>
  .app { height: 100%; display: grid; grid-template-columns: 260px minmax(0, 1fr); }
  .main {
    min-width: 0;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(360px, 1fr) minmax(0, 1.15fr);
    grid-template-rows: minmax(0, 1fr);
  }
  .chat-col { min-height: 0; min-width: 0; }
  .browser-col { min-height: 0; min-width: 0; padding: 12px 12px 12px 0; }
  .top { display: none; }
  .scrim { display: none; }
  .icon-btn { border: 0; background: none; padding: 7px; border-radius: 8px; color: var(--muted); display: inline-flex; }
  .icon-btn:hover { background: var(--hover); }

  @media (max-width: 900px) {
    .app { grid-template-columns: minmax(0, 1fr); }
    .main { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto auto minmax(0, 1fr); height: 100dvh; }
    .top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 8px 10px;
      font-weight: 500;
    }
    .top span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .browser-col { grid-row: 2; padding: 0 12px; height: 34vh; }
    .chat-col { grid-row: 3; }
    .scrim { display: block; position: fixed; inset: 0; z-index: 10; border: 0; background: rgba(0, 0, 0, 0.35); }
  }
</style>
