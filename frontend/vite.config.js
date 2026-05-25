import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // Split large deps into separate cacheable chunks.
    // Browser only re-downloads a chunk when IT changes,
    // not when app code changes.
    rollupOptions: {
      output: {
        manualChunks: {
          'react-vendor': ['react', 'react-dom'],
          'zustand': ['zustand'],
          'md-vendor': ['react-markdown', 'react-syntax-highlighter'],
        },
      },
    },
    // Raise warning threshold — syntax-highlighter is intentionally large
    chunkSizeWarningLimit: 1200,
  },
  // Use esbuild for both JS and CSS minification (faster than terser)
  esbuild: {
    target: 'es2020',
  },
})
