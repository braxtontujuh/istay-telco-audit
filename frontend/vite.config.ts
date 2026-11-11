import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [react(), VitePWA({
    registerType: 'prompt',
    includeAssets: ['icon.svg', 'icon-192.png', 'icon-512.png'],
    manifest: {
      name: 'I-Stay Telco Audit', short_name: 'I-Stay Audit',
      description: 'Mobile data inspection for I-Stay dormitories',
      theme_color: '#123c3b', background_color: '#f4f7f5',
      start_url: '/app', scope: '/', display: 'standalone',
      icons: [
        { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
        { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      ],
    },
    workbox: {
      globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
      navigateFallback: '/index.html', navigateFallbackDenylist: [/^\/api(?:\/|$)/],
      // Authenticated data belongs only in user-scoped IndexedDB, never runtime Cache Storage.
      runtimeCaching: [], cleanupOutdatedCaches: true,
      clientsClaim: true,
    },
  })],
  server: { port: 5173, strictPort: true },
});
