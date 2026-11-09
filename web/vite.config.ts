import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/** In `--mode visual` only, gives index.html the root's <base href>. */
function visualBase(): Plugin {
  let visual = false
  return { name: 'visual-base', configResolved: c => { visual = c.mode === 'visual' }, transformIndexHtml: html => (visual ? html.replace('<head>', '<head><base href="/">') : html) }
}

// `npm run build` writes into the Python package, so `./tubes serve` serves the built app.
// `npm run dev` runs the dev server with hot reload and proxies /api to a running `./tubes serve` (port 8367).
export default defineConfig({
  base: './',       // relative asset paths, so the app works at the server's root and behind a reverse proxy at a path (the server's <base> tag and api.ts BASE do the same for routes and the API)
  plugins: [
    react(), tailwindcss(),
    // The visual suite serves dist-visual from a plain static server, which cannot add the <base href> the
    // Python server gives every page (with_base in server/app.py). Without it a deep route such as
    // /channels/x would load its assets from /channels/assets/, so that build carries the root's tag itself.
    visualBase(),
  ],
  build: {
    outDir: '../src/tubes/server/static',
    emptyOutDir: true,
    // One bundle of about 520 kB (160 kB gzipped), most of it React, React Router, TanStack and Strata. A local app loads it once; split routes with lazy() when that stops being true.
    chunkSizeWarningLimit: 1000,
  },
  server: { proxy: { '/api': 'http://127.0.0.1:8367' } },
})
