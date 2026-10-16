import {parse} from '@babel/parser';
import {readdir, readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export function forbiddenImport(source, filename) {
  if (/^(storybook(?:\/|$)|@storybook\/)/.test(source) || /(?:^|\/)(?:stories|\.storybook)(?:\/|$)/.test(source)) return 'workbench dependency in production';
  if (source.startsWith('@base-ui/') && !filename.replaceAll('\\', '/').includes('/src/ui/')) return 'Base UI must stay behind canonical UI wrappers';
  return null;
}
export async function checkTree(directory) {
  const failures = [];
  for (const entry of await readdir(directory, {withFileTypes: true})) {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) {failures.push(...await checkTree(filename)); continue;}
    if (!/\.(?:jsx?|tsx?)$/.test(entry.name)) continue;
    const ast = parse(await readFile(filename, 'utf8'), {sourceType: 'module', plugins: ['jsx', 'typescript']});
    function visit(node) {
      if (!node || typeof node !== 'object') return;
      const source = ['ImportDeclaration', 'ExportNamedDeclaration', 'ExportAllDeclaration'].includes(node.type) ? node.source?.value : node.type === 'ImportExpression' ? node.source?.value : null;
      if (source) {const reason = forbiddenImport(source, filename); if (reason) failures.push(`${filename}: ${source}: ${reason}`);}
      for (const value of Object.values(node)) {
        if (Array.isArray(value)) value.forEach(visit);
        else if (value && typeof value === 'object') visit(value);
      }
    }
    visit(ast);
  }
  return failures;
}
if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const failures = await checkTree(fileURLToPath(new URL('../src', import.meta.url)));
  if (failures.length) {console.error(failures.join('\n')); process.exitCode = 1;}
  else console.log('Production/workbench and headless UI import boundaries passed.');
}
