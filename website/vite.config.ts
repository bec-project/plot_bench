import { defineConfig } from 'vite';
export default defineConfig({ base: process.env.PLOTBENCH_SITE_BASE || '/plot_bench/' });
