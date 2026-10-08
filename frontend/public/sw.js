const CACHE='fam-uh-le-v3';
const APP_SHELL=['/','/manifest.webmanifest','/brand/icon-192.png','/brand/icon-512.png'];

self.addEventListener('install',event=>{
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(APP_SHELL)));
});

self.addEventListener('activate',event=>{
  event.waitUntil(Promise.all([
    caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))),
    self.clients.claim(),
  ]));
});

function isPrivateRequest(request){
  const url=new URL(request.url);
  return url.origin!==self.location.origin || url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/') || url.pathname.startsWith('/share.html');
}

self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET'||isPrivateRequest(request))return;
  if(request.mode==='navigate'){
    event.respondWith(fetch(request).catch(()=>caches.match('/')));
    return;
  }
  event.respondWith(caches.match(request).then(cached=>cached||fetch(request).then(response=>{
    if(response.ok){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(request,copy));}
    return response;
  })));
});
