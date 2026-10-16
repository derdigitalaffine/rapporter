import {build} from 'vite';
import {gzipSync} from 'node:zlib';
import {writeFile} from 'node:fs/promises';

await build({build: {write: false}, plugins: [{
  name: 'familyos-bundle-report',
  async generateBundle(_, bundle) {
    const chunks = Object.values(bundle).filter(item => item.type === 'chunk');
    const byName = new Map(chunks.map(chunk => [chunk.fileName, chunk]));
    const initial = new Set();
    function visit(name) {if (initial.has(name)) return; initial.add(name); byName.get(name)?.imports.forEach(visit);}
    chunks.filter(chunk => chunk.isEntry).forEach(chunk => visit(chunk.fileName));
    const report = {
      initialBytes: chunks.filter(chunk => initial.has(chunk.fileName)).reduce((sum, chunk) => sum + Buffer.byteLength(chunk.code), 0),
      initialGzipBytes: chunks.filter(chunk => initial.has(chunk.fileName)).reduce((sum, chunk) => sum + gzipSync(chunk.code).length, 0),
      chunks: chunks.map(chunk => ({file: chunk.fileName, entry: chunk.isEntry, initial: initial.has(chunk.fileName), bytes: Buffer.byteLength(chunk.code), gzipBytes: gzipSync(chunk.code).length, imports: chunk.imports, dynamicImports: chunk.dynamicImports, modules: Object.entries(chunk.modules).map(([id, value]) => ({id: id.replace(`${process.cwd()}/`, ''), renderedBytes: value.renderedLength})).sort((a, b) => b.renderedBytes - a.renderedBytes)})).sort((a, b) => b.bytes - a.bytes),
    };
    await writeFile('bundle-report.json', `${JSON.stringify(report, null, 2)}\n`);
    console.log(`Initial JS: ${report.initialBytes} bytes / ${report.initialGzipBytes} gzip bytes. See bundle-report.json for import graph and module contributions.`);
  },
}]});
