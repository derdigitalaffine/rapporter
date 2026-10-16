import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {forbiddenImport, checkTree} from '../scripts/check-ui-boundaries.mjs';
test('workbench and Base UI imports are isolated', () => {
  for (const specifier of ['storybook/test', '@storybook/react-vite', '../stories/Test']) assert.ok(forbiddenImport(specifier, '/app/src/Feature.jsx'));
  assert.ok(forbiddenImport('@base-ui/react/dialog', '/app/src/Feature.jsx'));
  assert.equal(forbiddenImport('@base-ui/react/dialog', '/app/src/ui/FamilyDialog.jsx'), null);
  assert.equal(forbiddenImport('./form-primitives', '/app/src/Feature.jsx'), null);
});
test('production source respects import boundaries', async () => {
  assert.deepEqual(await checkTree(fileURLToPath(new URL('../src', import.meta.url))), []);
});
