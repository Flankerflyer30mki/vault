import process from 'node:process'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The browser only ever talks to this dev server; /api and /health are forwarded to Django, so the session
// cookie is first-party and there is no CORS. Host is passed through unchanged (no changeOrigin), which keeps
// Django's CSRF Origin check simple: Origin and Host both say localhost:5173.
const target = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target },
      '/health': { target },
    },
  },
})
