const CACHE='fam-uh-le-v6';
const STATIC_SHELL=['/manifest.webmanifest','/brand/icon-192.png','/brand/icon-512.png'];

async function cacheAppShell(){
  const cache=await caches.open(CACHE);
  await cache.addAll(STATIC_SHELL);
  const response=await fetch('/',{cache:'no-store'});
  if(!response.ok)throw new Error(`shell_${response.status}`);
  const html=await response.clone().text();
  await cache.put('/',response);
  const assets=[...html.matchAll(/(?:src|href)=["'](\/assets\/[^"']+)["']/g)].map(match=>match[1]);
  await Promise.all([...new Set(assets)].map(asset=>cache.add(asset)));
}

self.addEventListener('install',event=>{
  self.skipWaiting();
  event.waitUntil(cacheAppShell());
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
  const url=new URL(request.url);

  // Vite bundles are content-hashed. Network-first keeps deployments fresh while
  // the matching hashed bundle remains available when the device is offline.
  if(url.pathname.startsWith('/assets/')){
    event.respondWith(fetch(request).then(response=>{
      if(response.ok){const copy=response.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put(request,copy)))}
      return response;
    }).catch(()=>caches.match(request).then(cached=>cached||Response.error())));
    return;
  }

  if(request.mode==='navigate'){
    event.respondWith(fetch(request).then(response=>{
      if(response.ok){
        const copy=response.clone();
        event.waitUntil(caches.open(CACHE).then(cache=>cache.put('/',copy)));
      }
      return response;
    }).catch(()=>caches.match('/')));
    return;
  }

  event.respondWith(fetch(request).catch(()=>caches.match(request)));
});

self.addEventListener('push',event=>{
  let data={title:'fam-uh-le',body:'Neue Familienaktivität',url:'/',tag:'fam-uh-le'};
  try{if(event.data)data={...data,...event.data.json()}}catch{if(event.data)data.body=event.data.text()}
  event.waitUntil(self.registration.showNotification(data.title,{
    body:data.body,
    icon:'/brand/icon-192.png',
    badge:'/brand/icon-192-maskable.png',
    tag:data.tag,
    data:{url:data.url||'/'},
    renotify:false,
  }));
});

self.addEventListener('notificationclick',event=>{
  event.notification.close();
  const target=new URL(event.notification.data?.url||'/',self.location.origin).href;
  event.waitUntil(self.clients.matchAll({type:'window',includeUncontrolled:true}).then(clients=>{
    for(const client of clients){
      if(new URL(client.url).origin===self.location.origin){client.navigate(target);return client.focus();}
    }
    return self.clients.openWindow(target);
  }));
});
