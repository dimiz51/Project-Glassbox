<script>
  import emblaCarouselSvelte from 'embla-carousel-svelte'
  import Icon from './Icon.svelte'

  // Read-only view of the agent's sandbox browser: only the agent controls it.
  // view: 'live' | 'agent'; picked: index into shots for the agent view (null = latest)
  let { frame, url, shots, point, running, view = $bindable(), picked = $bindable() } = $props()

  const shown = $derived(shots.length ? shots[picked ?? shots.length - 1] : null)

  // step timeline carousel (Embla): drag or use the arrows; follows the newest / selected step
  let embla = $state()
  const carousel = { options: { align: 'end', containScroll: 'trimSnaps', dragFree: true }, plugins: [] }
  $effect(() => {
    const i = picked ?? shots.length - 1
    if (embla && shots.length) requestAnimationFrame(() => embla.scrollTo(i))
  })

  function pick(i) {
    picked = i
    view = 'agent'
  }
</script>

<section class="panel" aria-label="Sandbox browser">
  <div class="bar">
    <div class="url" title={url}>
      <Icon name="globe" />
      <span>{url || 'about:blank'}</span>
    </div>
    {#if running}<span class="live"><i></i>Agent driving</span>{/if}
    <div class="seg" role="tablist" aria-label="View">
      <button role="tab" aria-selected={view === 'live'} class:sel={view === 'live'} onclick={() => (view = 'live')}>Live</button>
      <button role="tab" aria-selected={view === 'agent'} class:sel={view === 'agent'} disabled={!shots.length} onclick={() => (view = 'agent')}>Agent view</button>
    </div>
  </div>

  <div class="screen">
    {#if view === 'agent' && shown}
      <div class="frame">
        <img src={shown.src} alt="Screenshot the model saw at step {shown.step}" />
        {#if shown.coordinate}
          <span class="target" style="left:{shown.coordinate[0] / 10}%; top:{shown.coordinate[1] / 10}%"></span>
        {/if}
      </div>
      <span class="caption">Step {shown.step} · what the model saw{shown.label ? ` → ${shown.label}` : ''}</span>
    {:else if frame}
      <div class="frame">
        <img src={frame} alt="Live view of the agent's sandbox browser" draggable="false" />
        {#if point}
          <!-- the agent's cursor: glides to each click target, ripples on click -->
          <div class="cursor" style="left:{point.at[0] / 10}%; top:{point.at[1] / 10}%">
            {#key point.step}<span class="ripple"></span>{/key}
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 2.5 19.5 11 12.6 12.6 9.6 19.5Z" /></svg>
            <b>step {point.step}</b>
          </div>
        {/if}
      </div>
    {:else}
      <div class="empty">
        <Icon name="browser" />
        <p>The sandbox browser shows up here.</p>
      </div>
    {/if}
  </div>

  {#if shots.length}
    <div class="timeline">
      <button class="arrow" onclick={() => embla?.scrollPrev()} aria-label="Earlier steps"><Icon name="chevron" /></button>
      <div class="embla" use:emblaCarouselSvelte={carousel} onemblaInit={(e) => (embla = e.detail)}>
        <div class="track" aria-label="What the agent saw, step by step">
          {#each shots as s, i (s.src)}
            <div class="slide">
              <button class="thumb" class:sel={view === 'agent' && (picked ?? shots.length - 1) === i} onclick={() => pick(i)} title={s.url}>
                <span class="img">
                  <img src={s.src} alt="" loading="lazy" draggable="false" />
                  {#if s.coordinate}<i style="left:{s.coordinate[0] / 10}%; top:{s.coordinate[1] / 10}%"></i>{/if}
                  <b>{s.step}</b>
                </span>
                <span class="what">{s.label ?? '…'}</span>
              </button>
            </div>
          {/each}
        </div>
      </div>
      <button class="arrow next" onclick={() => embla?.scrollNext()} aria-label="Later steps"><Icon name="chevron" /></button>
    </div>
  {/if}
</section>

<style>
  .panel {
    height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    background: var(--stage);
    border: 1px solid var(--line);
    border-radius: 16px;
    overflow: hidden;
  }

  .bar { display: flex; align-items: center; gap: 10px; padding: 10px; border-bottom: 1px solid var(--line); background: var(--bg); }
  .url {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--bubble);
    border-radius: 999px;
    padding: 6px 12px;
    color: var(--muted);
    font: 12.5px/1.3 var(--mono);
  }
  .url :global(.icon) { width: 14px; height: 14px; }
  .url span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink); }

  .live { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; color: var(--accent); white-space: nowrap; }
  .live i { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse { 50% { box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 25%, transparent); } }

  .seg { display: flex; background: var(--bubble); border-radius: 10px; padding: 3px; }
  .seg button { border: 0; background: none; color: var(--muted); font-size: 12.5px; font-weight: 500; padding: 4px 10px; border-radius: 7px; white-space: nowrap; }
  .seg button.sel { background: var(--bg); color: var(--ink); box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08); }
  .seg button:disabled { opacity: 0.4; }

  .screen { position: relative; flex: 1; min-height: 0; display: grid; place-items: center; padding: 14px; container-type: size; }
  .frame {
    position: relative;
    width: min(100cqw, 160cqh);
    aspect-ratio: 16 / 10;
    border-radius: 10px;
    overflow: hidden;
    box-shadow: var(--shadow);
    background: #fff;
  }
  .frame img { width: 100%; height: 100%; display: block; user-select: none; pointer-events: none; }
  .caption {
    position: absolute;
    left: 50%;
    bottom: 22px;
    transform: translateX(-50%);
    background: color-mix(in srgb, #000 70%, transparent);
    color: #fff;
    font-size: 12px;
    padding: 5px 10px;
    border-radius: 999px;
    white-space: nowrap;
    backdrop-filter: blur(6px);
  }

  /* where the model pointed: its 0-1000 coordinate as % of the frame */
  .target {
    position: absolute;
    width: 26px;
    height: 26px;
    margin: -13px 0 0 -13px;
    border-radius: 50%;
    background: color-mix(in srgb, var(--accent) 25%, transparent);
    border: 2px solid var(--accent);
    box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.8);
    pointer-events: none;
  }
  .cursor {
    position: absolute;
    width: 0;
    height: 0;
    pointer-events: none;
    transition: left 0.45s cubic-bezier(0.3, 0.7, 0.2, 1), top 0.45s cubic-bezier(0.3, 0.7, 0.2, 1);
  }
  .cursor svg {
    position: absolute;
    left: -3px;
    top: -2px;
    width: 26px;
    height: 26px;
    fill: var(--accent);
    stroke: #fff;
    stroke-width: 1.6;
    stroke-linejoin: round;
    filter: drop-shadow(0 2px 3px rgba(0, 0, 0, 0.35));
  }
  .cursor b {
    position: absolute;
    left: 20px;
    top: 20px;
    background: var(--accent);
    color: #fff;
    font: 500 10.5px/1 var(--mono);
    padding: 3px 6px;
    border-radius: 999px;
    white-space: nowrap;
  }
  .ripple {
    position: absolute;
    left: -18px;
    top: -18px;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    border: 2px solid var(--accent);
    animation: ripple 0.9s ease-out 0.4s both;
  }
  @keyframes ripple {
    from { transform: scale(0.3); opacity: 1; }
    to { transform: scale(1.6); opacity: 0; }
  }

  .empty { text-align: center; color: var(--faint); }
  .empty :global(.icon) { width: 36px; height: 36px; stroke-width: 1.5; }
  .empty p { margin: 8px 0 0; font-size: 14px; }

  .timeline { display: flex; align-items: center; gap: 4px; padding: 0 6px 12px; }
  .arrow {
    flex: none;
    border: 0;
    background: none;
    color: var(--muted);
    padding: 6px 2px;
    border-radius: 8px;
    display: inline-flex;
    transform: rotate(180deg);
  }
  .arrow.next { transform: none; }
  .arrow:hover { color: var(--ink); background: var(--hover); }
  .embla { overflow: hidden; flex: 1; min-width: 0; cursor: grab; }
  .embla:active { cursor: grabbing; }
  .track { display: flex; gap: 8px; touch-action: pan-y pinch-zoom; }
  .slide { flex: 0 0 auto; }
  .thumb { display: flex; flex-direction: column; gap: 4px; width: 120px; padding: 0; border: 0; background: none; text-align: left; }
  .thumb .img {
    position: relative;
    display: block;
    aspect-ratio: 16 / 10;
    border: 2px solid transparent;
    border-radius: 8px;
    overflow: hidden;
    background: var(--bubble);
  }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; opacity: 0.75; transition: opacity 0.15s; }
  .thumb:hover img, .thumb.sel img { opacity: 1; }
  .thumb.sel .img { border-color: var(--accent); }
  .thumb i {
    position: absolute;
    width: 8px;
    height: 8px;
    margin: -4px 0 0 -4px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 0 2px #fff;
  }
  .thumb b {
    position: absolute;
    left: 4px;
    bottom: 4px;
    background: color-mix(in srgb, #000 65%, transparent);
    color: #fff;
    font: 500 10px/1 var(--mono);
    padding: 3px 5px;
    border-radius: 5px;
  }
  .thumb .what {
    font: 11px/1.3 var(--mono);
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .thumb.sel .what { color: var(--ink); }

  @media (max-width: 1200px) {
    .live { display: none; }
  }
</style>
