// Same-origin integration-test host: production assets + real Django API.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
import {resolve,extname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(fileURLToPath(new URL('../frontend/dist',import.meta.url)));
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.webp':'image/webp','.woff2':'font/woff2','.json':'application/json','.webmanifest':'application/manifest+json'};
http.createServer(async(req,res)=>{
 if(['/api/','/caldav/','/calendar-feed/','/.well-known/caldav'].some(prefix=>req.url.startsWith(prefix))){
  const upstream=http.request({hostname:'127.0.0.1',port:8000,path:req.url,method:req.method,headers:req.headers},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res)});
  upstream.on('error',()=>{res.writeHead(502);res.end()});req.pipe(upstream);return;
 }
 const path=decodeURIComponent(new URL(req.url,'http://localhost').pathname),file=resolve(root,'.'+path);
 if(!file.startsWith(root+'/')&&file!==root){res.writeHead(403);res.end();return}
 try{const body=await readFile(path==='/'?resolve(root,'index.html'):file);res.writeHead(200,{'Content-Type':path==='/'?'text/html':types[extname(file)]||'application/octet-stream'});res.end(body)}catch{res.writeHead(200,{'Content-Type':'text/html'});res.end(await readFile(resolve(root,'index.html')))}
}).listen(4173,'127.0.0.1');
