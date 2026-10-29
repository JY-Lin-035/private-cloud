import { readFileSync, existsSync } from 'node:fs'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const BUILD_ID = existsSync('.buildid') ? readFileSync('.buildid', 'utf8').trim() : String(Date.now())

export default defineConfig({
  define: { __BUILD_TS__: JSON.stringify(BUILD_ID) },
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
