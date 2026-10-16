import {readFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const report=JSON.parse(await readFile(new URL('../bundle-report.json',import.meta.url),'utf8'));
assert.ok(report.initialBytes<2_000_000,`Initial JS budget exceeded: ${report.initialBytes} bytes (before splitting: 4,302,547)`);
const initialModules=report.chunks.filter(chunk=>chunk.initial).flatMap(chunk=>chunk.modules.map(module=>module.id));
for(const pattern of [/node_modules\/bwip-js\//,/node_modules\/@uiw\/react-md-editor\//,/node_modules\/maplibre-gl\//,/node_modules\/(?:@storybook\/|storybook\/)/,/src\/(?:VehiclesHub|NotesHub|LoyaltyCards|SettingsHub|StatisticsHub|TravelHub|PetCareHub|PregnancyBabyHub(?:V2)?)\.jsx$/]){
  assert.ok(!initialModules.some(id=>pattern.test(id)),`Deferred-only module leaked into initial graph: ${pattern}`);
}
console.log(`Bundle gate passed: ${report.initialBytes} initial bytes; heavy modules and workbench isolated.`);
