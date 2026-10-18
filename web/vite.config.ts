import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        // SU11A-46: library code in its own chunks, so the app chunk stays under
        // 500 kB and a deploy that changes only app code leaves the (long-cached)
        // vendor files untouched. Total bytes on a first visit are the same.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler|react-router|react-router-dom)[\\/]/.test(id)) return 'vendor-react';
          if (id.includes('@supabase')) return 'vendor-supabase';
          return 'vendor';
        },
      },
    },
  },
})
