<script>
  // Renders a typed error: human message, what to do next, technical detail on hover.
  let { error, compact = false } = $props()

  // `ollama serve` in hints -> <code>
  const parts = (t) => (t || '').split('`').map((text, i) => ({ text, code: i % 2 === 1 }))
</script>

<span class="err" class:compact title={error.detail || error.code}>
  <span class="msg">{error.message}</span>
  {#if error.hint}
    <span class="hint">
      {#each parts(error.hint) as p}{#if p.code}<code>{p.text}</code>{:else}{p.text}{/if}{/each}
    </span>
  {/if}
</span>

<style>
  .err { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .msg { color: var(--warn); font-weight: 500; }
  .hint { color: var(--muted); }
  .compact .msg { font-weight: 400; }
  code { font-family: var(--mono); font-size: 0.9em; background: var(--bubble); padding: 0 4px; border-radius: 4px; }
</style>
