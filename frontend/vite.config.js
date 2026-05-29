import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ isSsrBuild }) => ({
  plugins: [react()],
  build: {
    // SSR build: выводим в dist/server/, клиентский build — в dist/client/
    outDir: isSsrBuild ? 'dist/server' : 'dist/client',
    rollupOptions: isSsrBuild
      ? { input: '/src/entry-server.jsx' }
      : undefined,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
}));
