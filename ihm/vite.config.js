import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    // Développement local uniquement : en production, nginx fait ce rôle sur le port 8080.
    proxy: { '/api': 'http://localhost:8000' },
  },
})
