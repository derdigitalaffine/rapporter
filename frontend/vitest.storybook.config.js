import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {defineConfig} from 'vitest/config';
import {storybookTest} from '@storybook/addon-vitest/vitest-plugin';
import {playwright} from '@vitest/browser-playwright';

const dirname = path.dirname(fileURLToPath(import.meta.url));
export default defineConfig({
  test: {projects: [{
    plugins: [storybookTest({configDir: path.join(dirname, '.storybook')})],
    test: {
      name: 'storybook',
      browser: {enabled: true, headless: true, screenshotDirectory: 'workbench-results/vitest', provider: playwright(), instances: [{browser: 'chromium'}]},
    },
  }]},
});
