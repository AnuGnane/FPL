/// <reference types="vitest" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The build lands inside the Python package so the wheel can ship it and
// FastAPI can serve it from importlib.resources (see src/gaffer/web/app.py).
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../src/gaffer/web/static', emptyOutDir: true },
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8927', changeOrigin: true } },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './vitest.setup.ts',
    css: false,
  },
})
