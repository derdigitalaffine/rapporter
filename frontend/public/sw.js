const CACHE='fam-uh-le-v4';
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
