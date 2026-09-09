import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import preact from '@preact/preset-vite';
import { defineConfig } from 'vite';
import { viteSingleFile } from 'vite-plugin-singlefile';

const here = dirname(fileURLToPath(import.meta.url));

// The source controls page is served as a single file at "/" by both the Python
// and Rust sources (neither serves extra asset routes), so JS and CSS are inlined.
// Output lands in ./dist and the build script copies it over the shipped
// core/src/plotbench/controls.html.
export default defineConfig({
  base: './',
  plugins: [preact(), viteSingleFile()],
  build: {
    outDir: resolve(here, 'dist'),
    emptyOutDir: true,
    target: 'es2022',
    minify: false,
    rollupOptions: { input: resolve(here, 'controls.html') },
  },
});
