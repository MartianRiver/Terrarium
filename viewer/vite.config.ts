import { defineConfig } from 'vite';

// three.js alone is ~600 kB minified; that's expected here
export default defineConfig(({ mode }) => ({
  build: {
    chunkSizeWarningLimit: 800,
    // the public site is the viewer alone
    rolldownOptions: { input: mode === 'site' ? ['index.html'] : ['index.html', 'runs.html'] },
  },
  // the runs page reads training runs from `python -m terrarium.serve`
  server: { proxy: { '/api': 'http://127.0.0.1:5190' } },
}));
