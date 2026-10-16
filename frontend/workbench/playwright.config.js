import {defineConfig} from '@playwright/test';
export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.js',
  outputDir: '../workbench-results',
  reporter: [['line'], ['html', {outputFolder: 'workbench-report', open: 'never'}]],
  use: {baseURL: 'http://127.0.0.1:6006', trace: 'retain-on-failure', screenshot: 'only-on-failure', serviceWorkers: 'block'},
  projects: [320, 390, 1024, 1440].map(width => ({name: `${width}px`, use: {viewport: {width, height: 900}, reducedMotion: 'reduce'}})),
  webServer: {command: 'npx vite preview --outDir storybook-static --host 127.0.0.1 --port 6006 --strictPort', url: 'http://127.0.0.1:6006', reuseExistingServer: !process.env.CI},
});
