import { defineConfig } from 'vite';

// three.js alone is ~600 kB minified; that's expected for a local viewer
export default defineConfig({
  build: { chunkSizeWarningLimit: 800 },
});
