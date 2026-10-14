export function appScrollTarget(){
 return document.documentElement.hasAttribute('data-app-standalone')
  ?document.querySelector('.app-shell>.content')||window
  :window;
}

export function scrollAppTo(options){appScrollTarget().scrollTo(options)}

export function scrollAppNearEdge(clientY){
 const target=appScrollTarget();
 const bounds=target===window?{top:0,bottom:window.innerHeight,height:window.innerHeight}:target.getBoundingClientRect();
 const edge=Math.min(96,Math.max(56,bounds.height*.12));
 if(clientY<bounds.top+edge)target.scrollBy(0,-Math.max(8,Math.ceil((bounds.top+edge-clientY)/4)));
 else if(clientY>bounds.bottom-edge)target.scrollBy(0,Math.max(8,Math.ceil((clientY-(bounds.bottom-edge))/4)));
}
