import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Built output lands inside ../weather, which Caddy already bind-mounts at
// /srv/weather. That means the new client is reachable at /worldtwin/v2/ with
// no Caddyfile edit and no container restart — the shared ingress serves paying
// tenants, so not touching it is worth more than a tidier path.
export default defineConfig({
  base: '/worldtwin/v2/',
  plugins: [react(), tailwindcss()],
  build: {
    outDir: '../weather/v2',
    emptyOutDir: true,
    target: 'es2022',
  },
  server: {
    // `npm run dev` proxies to the live aggregator so development uses real data.
    proxy: {
      '/api': { target: 'http://127.0.0.1', changeOrigin: true },
      '/v1': { target: 'http://127.0.0.1', changeOrigin: true },
    },
  },
})
