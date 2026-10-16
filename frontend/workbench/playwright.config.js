import {defineConfig} from '@playwright/test';
import {fileURLToPath} from 'node:url';
export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.js',
  outputDir: '../workbench-results',
  reporter: [['line'], ['html', {outputFolder: fileURLToPath(new URL('../workbench-report', import.meta.url)), open: 'never'}]],
  use: {baseURL: 'http://127.0.0.1:6006', trace: 'retain-on-failure', screenshot: 'only-on-failure', serviceWorkers: 'block'},
  projects: [[320,568], [390,844], [1024,768], [1440,900]].map(([width,height]) => ({name: `${width}px`, use: {viewport: {width,height}, reducedMotion: 'reduce'}})),
  webServer: {cwd: fileURLToPath(new URL('..', import.meta.url)), command: 'npx vite preview --outDir storybook-static --host 127.0.0.1 --port 6006 --strictPort', url: 'http://127.0.0.1:6006/iframe.html', reuseExistingServer: !process.env.CI},
});
