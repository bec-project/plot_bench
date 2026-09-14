import { defineConfig } from 'vite';

// GitHub Pages serves the project site under /<repository>/, so the workflow
// sets PLOTBENCH_SITE_BASE from the repository name; a custom domain uses '/'.
// Hash navigation keeps every page reachable without server-side routing.
export default defineConfig({
  base: process.env.PLOTBENCH_SITE_BASE || '/plot_bench/',
  server: { host: '127.0.0.1', port: 5373, strictPort: true },
  preview: { host: '127.0.0.1', port: 4373, strictPort: true },
  build: { target: 'es2022' },
});
