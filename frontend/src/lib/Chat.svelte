<script>
  import { tick } from 'svelte'
  import { marked } from 'marked'
  import DOMPurify from 'dompurify'
  import Icon from './Icon.svelte'
  import ErrorText from './ErrorText.svelte'

  let { messages, running, ready, notice, ondismiss, onsend, onstop, onpickstep } = $props()

  const SUGGESTIONS = [
    { title: 'Flights under 10,000 SEK', text: 'Open skyscanner.se, find one-way flights from Stockholm to Chicago on 25 November and tell me my options below 10,000 SEK' },
    { title: 'Cheapest flight on Google Flights', text: 'Go to google.com/travel/flights and find the cheapest one-way flight Stockholm → Chicago on 25 November' },
    { title: 'Summarise Hacker News', text: 'Open news.ycombinator.com and summarise the top 5 stories' },
  ]

  let prompt = $state('')
  let toggled = $state({}) // run index -> expanded override
  let logEl = $state()
  let inputEl = $state()

  const md = (t) => DOMPurify.sanitize(marked.parse(t || '', { breaks: true }))
  const host = (u) => {
    try {
      return new URL(u).host || u
    } catch {
      return u
    }
  }
  const dur = (s) => (s >= 60 ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s` : `${Math.round(s)}s`)
  const isOpen = (m, i) => toggled[i] ?? m.status === 'running'

  function send(text = prompt) {
    text = text.trim()
    if (!text || !ready) return
    onsend(text)
    prompt = ''
    resize()
  }

  function onKey(e) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault()
      send()
    }
  }

  function resize() {
    tick().then(() => {
      if (!inputEl) return
      inputEl.style.height = 'auto'
      inputEl.style.height = Math.min(inputEl.scrollHeight, 200) + 'px'
    })
  }

  // keep the newest content in view
  $effect(() => {
    JSON.stringify(messages)
    tick().then(() => logEl?.scrollTo({ top: logEl.scrollHeight, behavior: 'smooth' }))
  })
</script>

<section class="chat" class:empty={!messages.length}>
  {#if notice}
    <div class="notice" role="alert">
      <ErrorText error={notice} />
      <button onclick={ondismiss} aria-label="Dismiss"><Icon name="close" /></button>
    </div>
  {/if}
  {#if messages.length}
    <div class="log" bind:this={logEl}>
      <div class="col">
        {#each messages as m, i}
          {#if m.role === 'user'}
            <div class="user">{m.text}</div>
          {:else}
            <div class="agent">
              <button class="work" onclick={() => (toggled[i] = !isOpen(m, i))} aria-expanded={isOpen(m, i)}>
                {#if m.status === 'running'}<span class="spin" aria-hidden="true"></span>{/if}
                <span>
                  {m.status === 'running' ? 'Browsing' : 'Browsed'}{m.steps ? ` · ${m.steps} step${m.steps > 1 ? 's' : ''}` : ''}{m.seconds ? ` · ${dur(m.seconds)}` : ''}
                </span>
                <span class="chev" class:down={isOpen(m, i)}><Icon name="chevron" /></span>
              </button>

              {#if isOpen(m, i)}
                <ol class="steps">
                  {#each m.items as it}
                    {#if it.kind === 'step' && !it.talk}
                      <li class:err={it.error}>
                        <span class="n">{it.n}</span>
                        <div class="story">
                          <figure class="obs">
                            <figcaption>Observation (before action)</figcaption>
                            <button class="peek" onclick={() => onpickstep(it.shot)} title="Open in Agent view">
                              <img src={it.shot} alt="Page the agent saw at step {it.n}" loading="lazy" />
                              {#if it.coordinate}<i style="left:{it.coordinate[0] / 10}%; top:{it.coordinate[1] / 10}%"></i>{/if}
                            </button>
                          </figure>

                          {#if it.label}
                            <div class="did">
                              <code>{it.label}</code>
                              <p>{it.thought}</p>
                            </div>
                          {:else}
                            <code class="pending">Deciding what to do on {host(it.url)}</code>
                          {/if}
                          {#if it.error}<p class="e"><ErrorText error={it.error} compact /></p>{/if}

                          {#if it.after}
                            <figure class="obs">
                              <figcaption>Observation (after action)</figcaption>
                              <button class="peek" onclick={() => onpickstep(it.after)} title="Open in Agent view">
                                <img src={it.after} alt="Page after step {it.n}" loading="lazy" />
                              </button>
                            </figure>
                          {/if}
                        </div>
                      </li>
                    {:else if it.kind === 'user'}
                      <li class="steer"><span>You</span>{it.text}</li>
                    {/if}
                  {/each}
                </ol>
              {/if}

              {#each m.items.filter((it) => it.kind === 'message') as it}
                <div class="md">{@html md(it.text)}</div>
              {/each}

              {#if m.answer}
                <div class="md">{@html md(m.answer)}</div>
              {:else if m.status === 'stopped'}
                <p class="note">Stopped.</p>
              {:else if m.status === 'error'}
                <div class="note"><ErrorText error={m.error} /></div>
              {/if}
            </div>
          {/if}
        {/each}
      </div>
    </div>
  {:else}
    <div class="hero">
      <h1>What should I look up?</h1>
      <p>Prompt your local model, which controls a headless browser to perform a task.</p>
    </div>
  {/if}

  <div class="dock">
    <form
      class="composer"
      onsubmit={(e) => {
        e.preventDefault()
        send()
      }}>
      <textarea
        bind:this={inputEl}
        bind:value={prompt}
        oninput={resize}
        onkeydown={onKey}
        rows="1"
        placeholder={running ? 'Steer the agent, e.g. "only direct flights"' : messages.length ? 'Ask a follow-up' : 'Ask the agent to find something on the web'}
      ></textarea>
      {#if running && !prompt.trim()}
        <button type="button" class="round" onclick={onstop} aria-label="Stop"><Icon name="stop" /></button>
      {:else}
        <button type="submit" class="round" disabled={!prompt.trim() || !ready} aria-label="Send"><Icon name="up" /></button>
      {/if}
    </form>

    {#if !messages.length}
      <div class="sugg">
        {#each SUGGESTIONS as s}
          <button onclick={() => send(s.text)} disabled={!ready} title={s.text}>{s.title}</button>
        {/each}
      </div>
    {:else}
      <p class="hint">The agent can make mistakes. Every step is saved in session_blob/.</p>
    {/if}
  </div>
</section>

<style>
  .chat { height: 100%; min-height: 0; display: flex; flex-direction: column; }
  .chat.empty { justify-content: center; padding-bottom: 12vh; }

  .log { flex: 1; min-height: 0; overflow-y: auto; scrollbar-width: thin; }
  .col { max-width: 720px; margin: 0 auto; padding: 24px 24px 8px; display: flex; flex-direction: column; gap: 22px; }

  .user {
    align-self: flex-end;
    max-width: 80%;
    background: var(--bubble);
    padding: 10px 16px;
    border-radius: 20px;
    white-space: pre-wrap;
    animation: rise 0.2s ease-out;
  }
  @keyframes rise { from { opacity: 0; transform: translateY(4px); } }

  .agent { display: flex; flex-direction: column; gap: 10px; animation: rise 0.2s ease-out; }
  .work {
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border: 0;
    background: none;
    padding: 2px 0;
    color: var(--muted);
    font-size: 14px;
    font-weight: 500;
  }
  .work:hover { color: var(--ink); }
  .chev { display: inline-flex; transition: transform 0.15s; }
  .chev :global(.icon) { width: 15px; height: 15px; }
  .chev.down { transform: rotate(90deg); }
  .spin {
    width: 13px;
    height: 13px;
    border: 2px solid var(--line);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .steps {
    list-style: none;
    margin: 0;
    padding: 2px 0 2px 14px;
    border-left: 2px solid var(--line);
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  .steps li { display: flex; gap: 10px; align-items: flex-start; font-size: 13.5px; }
  .n {
    flex: none;
    min-width: 22px;
    height: 22px;
    display: grid;
    place-items: center;
    border: 1px solid var(--line);
    background: var(--bg);
    border-radius: 6px;
    font: 500 11px/1 var(--mono);
    color: var(--muted);
  }
  li.err .n { border-color: var(--warn); color: var(--warn); }
  .steps code { font: 500 12.5px/1.5 var(--mono); word-break: break-all; }
  .steps code.pending { color: var(--muted); }
  .steps code.pending::after { content: '…'; }
  .steps p { margin: 1px 0 0; color: var(--muted); line-height: 1.45; }
  .steps p.e, .note.e { color: var(--warn); }
  .story { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 8px; }
  .obs { margin: 0; display: flex; flex-direction: column; gap: 4px; }
  .obs figcaption { font-size: 12px; font-weight: 500; color: var(--muted); }
  .did { border-left: 2px solid var(--accent); padding-left: 10px; }
  .peek {
    position: relative;
    width: min(280px, 100%);
    aspect-ratio: 16 / 10;
    padding: 0;
    border: 1px solid var(--line);
    border-radius: 8px;
    overflow: hidden;
    background: var(--bubble);
  }
  .peek:hover { border-color: var(--accent); }
  .peek img { width: 100%; height: 100%; object-fit: cover; display: block; }
  /* where the model pointed (0-1000 grid as % of the image) */
  .peek i {
    position: absolute;
    width: 12px;
    height: 12px;
    margin: -6px 0 0 -6px;
    border-radius: 50%;
    background: color-mix(in srgb, var(--accent) 35%, transparent);
    border: 2px solid var(--accent);
    box-shadow: 0 0 0 2px #fff;
  }
  .steer { color: var(--muted); font-style: italic; }
  .steer span { font: 500 11px/22px var(--mono); font-style: normal; color: var(--accent); }

  .md { line-height: 1.65; }
  .md :global(p) { margin: 0 0 10px; }
  .md :global(:last-child) { margin-bottom: 0; }
  .md :global(ul), .md :global(ol) { padding-left: 22px; margin: 0 0 10px; }
  .md :global(table) { border-collapse: collapse; width: 100%; font-size: 14px; margin: 4px 0 10px; }
  .md :global(th), .md :global(td) { border-bottom: 1px solid var(--line); padding: 6px 8px; text-align: left; }
  .md :global(a) { color: var(--accent); }
  .md :global(code) { font-family: var(--mono); font-size: 0.88em; background: var(--bubble); padding: 1px 5px; border-radius: 5px; }
  .note { margin: 0; color: var(--muted); font-size: 14px; }
  .notice {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    justify-content: space-between;
    max-width: 720px;
    width: calc(100% - 48px);
    margin: 16px auto 0;
    padding: 12px 14px;
    border: 1px solid color-mix(in srgb, var(--warn) 35%, var(--line));
    background: color-mix(in srgb, var(--warn) 6%, var(--bg));
    border-radius: 12px;
    font-size: 14px;
  }
  .notice button { border: 0; background: none; color: var(--muted); padding: 2px; border-radius: 6px; display: inline-flex; }
  .notice button:hover { color: var(--ink); }
  .chat.empty .notice { position: absolute; top: 0; left: 0; right: 0; }
  .chat { position: relative; }

  .hero { text-align: center; padding: 0 24px 24px; }
  .hero h1 { font-size: 28px; font-weight: 600; letter-spacing: -0.02em; margin: 0 0 6px; }
  .hero p { color: var(--muted); margin: 0; }

  .dock { width: 100%; max-width: 768px; margin: 0 auto; padding: 8px 24px 14px; }
  .composer {
    display: flex;
    align-items: flex-end;
    gap: 8px;
    background: var(--bubble);
    border-radius: 26px;
    padding: 8px 8px 8px 20px;
    border: 1px solid transparent;
    transition: border-color 0.15s;
  }
  .composer:focus-within { border-color: var(--line); }
  textarea {
    flex: 1;
    resize: none;
    border: 0;
    background: none;
    outline: none;
    padding: 8px 0;
    line-height: 1.5;
    max-height: 200px;
  }
  textarea::placeholder { color: var(--faint); }
  .round {
    width: 36px;
    height: 36px;
    flex: none;
    border-radius: 50%;
    border: 0;
    background: var(--ink);
    color: var(--bg);
    display: grid;
    place-items: center;
  }
  .round:disabled { opacity: 0.25; }

  .sugg { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin-top: 14px; }
  .sugg button {
    border: 1px solid var(--line);
    background: var(--bg);
    border-radius: 999px;
    padding: 7px 14px;
    font-size: 13.5px;
    color: var(--muted);
  }
  .sugg button:hover:not(:disabled) { color: var(--ink); background: var(--hover); }
  .hint { text-align: center; font-size: 12px; color: var(--faint); margin: 8px 0 0; }

  @media (max-width: 900px) {
    .col, .dock { padding-left: 16px; padding-right: 16px; }
  }
</style>
