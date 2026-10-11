import {createHash} from 'node:crypto';
import {readFile,readdir,writeFile} from 'node:fs/promises';
import {join,relative} from 'node:path';
import {fileURLToPath} from 'node:url';

const distDir=fileURLToPath(new URL('../dist/',import.meta.url));
const workerPath=join(distDir,'sw.js');

async function filesUnder(directory){
  const entries=await readdir(directory,{withFileTypes:true});
  const files=[];
  for(const entry of entries){
    const path=join(directory,entry.name);
    if(entry.isDirectory())files.push(...await filesUnder(path));
    else if(entry.isFile())files.push(path);
  }
  return files;
}

const files=(await filesUnder(distDir)).filter(path=>path!==workerPath).sort();
const hash=createHash('sha256');
for(const path of files){
  hash.update(relative(distDir,path));
  hash.update('\0');
  hash.update(await readFile(path));
  hash.update('\0');
}
const buildId=hash.digest('hex').slice(0,12);
const worker=await readFile(workerPath,'utf8');
const stamped=worker.replaceAll('__BUILD_ID__',buildId);
if(stamped===worker)throw new Error('Service worker build placeholder missing.');
await writeFile(workerPath,stamped,'utf8');
console.log(`Stamped service worker build ${buildId}`);
