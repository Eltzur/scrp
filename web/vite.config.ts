import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import { HOST_HTML_FILES, renderHostHtml } from './src/utils/hostHtml'

/**
 * SU11A-81 (SU11A-79 H5): one static HTML per host for crawlers that do not
 * run JS. index.html gets the portal's head values, index.super.html (served by
 * nginx on super.xxl.co.il, deploy/nginx/xxl-spa-super.conf) the super values.
 * Both reference the same hashed assets. See src/utils/hostHtml.ts.
 */
function hostHtml(): Plugin {
  return {
    name: 'xxl-host-html',
    apply: 'build',
    enforce: 'post',
    generateBundle(_options, bundle) {
      const index = bundle['index.html']
      if (!index || index.type !== 'asset') {
        this.error('xxl-host-html: the build has no index.html')
        return
      }
      const built = String(index.source)
      index.source = renderHostHtml(built, 'portal')
      this.emitFile({ type: 'asset', fileName: HOST_HTML_FILES.super, source: renderHostHtml(built, 'super') })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), hostHtml()],
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
