import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      // OCR assets (~7 MB) load on demand; don't precache them for every visitor
      workbox: { globIgnores: ['ocr/**'] },
      manifest: {
        name: 'Vaulta',
        short_name: 'Vaulta',
        description: 'Personal Finance AI for India',
        theme_color: '#0D0D14',
        background_color: '#0D0D14',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
})