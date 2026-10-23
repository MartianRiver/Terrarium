import { defineConfig } from 'vite';

// three.js alone is ~600 kB minified; that's expected for a local viewer
export default defineConfig({
  build: {
    chunkSizeWarningLimit: 800,
    rolldownOptions: { input: ['index.html', 'runs.html'] },
  },
  // the runs page reads training runs from `python -m terrarium.serve`
  server: { proxy: { '/api': 'http://127.0.0.1:5190' } },
});
