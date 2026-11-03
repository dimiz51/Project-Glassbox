<script>
  let { name } = $props()

  const paths = {
    plus: 'M12 5v14M5 12h14',
    edit: 'M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z',
    trash: 'M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14',
    up: 'M12 19V5M5 12l7-7 7 7',
    globe: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18',
    chevron: 'm9 6 6 6-6 6',
    sidebar: 'M4 4h16v16H4zM9 4v16',
    browser: 'M3 5h18v14H3zM3 9h18',
    close: 'M6 6l12 12M18 6 6 18',
  }
</script>

{#if name === 'stop'}
  <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" /></svg>
{:else}
  <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d={paths[name]} />
  </svg>
{/if}
