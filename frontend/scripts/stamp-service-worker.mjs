import {createHash} from 'node:crypto';
import {readFile,writeFile} from 'node:fs/promises';

const indexPath=new URL('../dist/index.html',import.meta.url);
const workerPath=new URL('../dist/sw.js',import.meta.url);
const index=await readFile(indexPath);
const worker=await readFile(workerPath,'utf8');
const buildId=createHash('sha256').update(index).digest('hex').slice(0,12);
const stamped=worker.replaceAll('__BUILD_ID__',buildId);
if(stamped===worker)throw new Error('Service worker build placeholder missing.');
await writeFile(workerPath,stamped,'utf8');
console.log(`Stamped service worker build ${buildId}`);
