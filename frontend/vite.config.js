import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// Local dev: `npm run dev` proxies /api (incl. the live-view websocket) to the FastAPI backend.
export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: { '/api': { target: process.env.API_URL || 'http://localhost:8000', ws: true } },
  },
})
