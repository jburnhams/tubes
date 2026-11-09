import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Storybook's own Vite config: the app's plugins without its build target or dev proxy.
export default defineConfig({ plugins: [react(), tailwindcss()] })
