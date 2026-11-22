import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// In development the API (uvicorn, port 8000) is reached through this proxy, so the browser sees one
// origin and no CORS setup is needed. In production set VITE_API_BASE to the deployed API URL and
// CORS_ORIGINS on the backend.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
  test: { environment: 'jsdom', globals: true, setupFiles: './src/test/setup.ts' },
})
