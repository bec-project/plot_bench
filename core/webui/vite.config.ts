import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import preact from '@preact/preset-vite';
import { defineConfig } from 'vite';

const here = dirname(fileURLToPath(import.meta.url));

// The built bundle is committed under the Python package so `plotbench matrix`
// runs with no Node toolchain. Fixed asset names keep the server's strict
// same-origin allow-list (index.html / editor.js / style.css) and CSP intact.
export default defineConfig({
  base: '/',
  plugins: [preact()],
  // During `npm run dev`, run `plotbench matrix --port 8799 --no-open` alongside so
  // the API calls reach a real editor server. The shipped build is served entirely
  // by that Python server, so this proxy affects development only.
  server: {
    host: '127.0.0.1',
    port: 5273,
    strictPort: true,
    // Preserve Host alongside Origin so the editor's same-origin check also
    // works through Vite. Its string proxy shorthand rewrites Host by default.
    proxy: { '/api': { target: 'http://127.0.0.1:8799', changeOrigin: false } },
  },
  build: {
    outDir: resolve(here, '../src/plotbench/matrix_assets'),
    emptyOutDir: true,
    target: 'es2022',
    minify: false,
    cssCodeSplit: false,
    assetsInlineLimit: 0,
    modulePreload: { polyfill: false },
    rollupOptions: {
      output: {
        entryFileNames: 'editor.js',
        chunkFileNames: 'editor.js',
        assetFileNames: 'style.css',
      },
    },
  },
});
