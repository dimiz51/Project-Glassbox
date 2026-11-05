<script>
  import Icon from './Icon.svelte'
  import ErrorText from './ErrorText.svelte'

  let { sessions, activeId, health, open = $bindable(), onselect, oncreate, ondelete } = $props()

  const PROVIDERS = { openai: 'OpenAI · cloud', openrouter: 'OpenRouter · cloud', ollama: 'Ollama · running locally' }
</script>

<aside class="side" class:open>
  <div class="head">
    <span class="brand">Project Glassbox</span>
    <button class="icon-btn mobile-only" onclick={() => (open = false)} aria-label="Close sidebar"><Icon name="close" /></button>
  </div>

  <button class="new" onclick={oncreate}>
    <Icon name="edit" /> New chat
  </button>

  <nav aria-label="Sessions">
    {#if sessions.length}
      <p class="label">Sessions</p>
    {/if}
    {#each sessions as s (s.session_id)}
      <div class="item" class:active={s.session_id === activeId}>
        <button class="pick" onclick={() => onselect(s.session_id)} title={s.title}>
          {#if s.running}<span class="dot" aria-label="Running"></span>{/if}
          <span class="title">{s.title}</span>
        </button>
        <button class="del" onclick={() => ondelete(s.session_id)} aria-label="Delete session"><Icon name="trash" /></button>
      </div>
    {/each}
  </nav>

  <footer class="model" title={health?.url || ''}>
    <span class="status" class:bad={health && !health.ok}></span>
    <div>
      {#if !health}
        <small>Checking the model…</small>
      {:else if health.ok}
        <strong>{health.model}</strong>
        <small>{PROVIDERS[health.provider] ?? health.provider}</small>
      {:else}
        {#if health.model}<strong>{health.model}</strong>{/if}
        <small class="problem"><ErrorText error={health.error} compact /></small>
      {/if}
    </div>
  </footer>
</aside>

<style>
  .side {
    height: 100%;
    display: flex;
    flex-direction: column;
    background: var(--side);
    padding: 12px 10px;
    min-width: 0;
  }
  .head { display: flex; align-items: center; justify-content: space-between; padding: 6px 8px 12px; }
  .brand { font-weight: 700; font-size: 17px; letter-spacing: -0.01em; }

  .new {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    border: 0;
    background: none;
    padding: 9px 10px;
    border-radius: 10px;
    font-weight: 500;
    font-size: 14px;
    text-align: left;
  }
  .new:hover { background: var(--hover); }

  nav { flex: 1; overflow-y: auto; margin-top: 12px; scrollbar-width: thin; }
  .label { font-size: 12px; font-weight: 500; color: var(--muted); padding: 0 10px; margin: 8px 0 4px; }
  .item { position: relative; display: flex; align-items: center; border-radius: 10px; }
  .item:hover, .item.active { background: var(--hover); }
  .pick {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    border: 0;
    background: none;
    padding: 8px 10px;
    font-size: 14px;
    text-align: left;
  }
  .title { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--accent);
    flex: none;
    animation: pulse 1.2s ease-in-out infinite;
  }
  @keyframes pulse { 50% { opacity: 0.35; } }
  .del {
    border: 0;
    background: none;
    color: var(--muted);
    padding: 6px 8px;
    border-radius: 8px;
    opacity: 0;
  }
  .item:hover .del, .item.active .del, .del:focus-visible { opacity: 1; }
  .del:hover { color: var(--warn); }
  .del :global(.icon) { width: 15px; height: 15px; }

  .model {
    display: flex;
    gap: 10px;
    align-items: center;
    padding: 10px;
    border-top: 1px solid var(--line);
    margin-top: 8px;
  }
  .model div { min-width: 0; display: flex; flex-direction: column; line-height: 1.3; }
  .model strong { font: 500 13px var(--mono); }
  .model small { color: var(--muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .model small.problem { white-space: normal; line-height: 1.4; }
  .status { align-self: flex-start; margin-top: 5px; }
  .status { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); flex: none; }
  .status.bad { background: var(--warn); }

  .icon-btn { border: 0; background: none; padding: 6px; border-radius: 8px; color: var(--muted); }
  .icon-btn:hover { background: var(--hover); }
  .mobile-only { display: none; }

  @media (max-width: 900px) {
    .side {
      position: fixed;
      inset: 0 auto 0 0;
      width: 280px;
      z-index: 20;
      transform: translateX(-100%);
      transition: transform 0.2s ease;
      box-shadow: var(--shadow);
    }
    .side.open { transform: none; }
    .mobile-only { display: inline-flex; }
  }
</style>
