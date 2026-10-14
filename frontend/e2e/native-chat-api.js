export async function installNativeChatMocks(page){
 const requests=[];
 const base={kind:'group',family_id:'family-1',state:'active',muted:false,revision:1,last_read_sequence:0,unread:0,last_message:null,participants:[{id:1,display_name:'Alex',state:'active'},{id:2,display_name:'Sam',state:'active'}],typing:[],read_receipts:[]};
 const family={...base,id:'family-chat',channel:'family',title:'Familie',can_send:true};
 const system={...base,id:'system-chat',channel:'system',title:'System',can_send:false,unread:1};
 const rows={'family-chat':[],'system-chat':[{id:'system-message',sender_id:0,sender_name:'FamilyOS',client_id:'system-initial',sequence:1,event_sequence:1,body:'Fenster schließen',created_at:new Date().toISOString(),edited:false,deleted:false,reply:null,attachments:[],reactions:[]}]};
 system.last_message=rows['system-chat'][0];
 await page.route('**/api/chat/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname,method=request.method();requests.push({path,method});
  const json=(body,status=200)=>route.fulfill({json:body,status});
  if(path==='/api/chat/account/')return json({user_id:1,display_name:'Alex',locale:'de',can_chat:true,push_enabled:true,read_receipts:true});
  if(path==='/api/chat/contacts/')return json({friends:[],incoming:[],outgoing:[],blocked:[]});
  if(path==='/api/chat/family-contacts/')return json({results:[],derived_friendship_ids:[]});
  if(path==='/api/chat/conversations/')return json({results:[family,system]});
  const id=path.split('/')[4],chat=[family,system].find(row=>row.id===id);
  if(!chat)return json({},404);
  if(path.endsWith('/messages/')){
   if(method==='POST'){
    if(!chat.can_send)return json({detail:'Read only'},403);
    const body=request.postData()||'';
    const message={id:'family-message-'+(rows[id].length+1),sender_id:1,sender_name:'Alex',client_id:body.match(/name="client_id"\r\n\r\n([^\r]+)/)?.[1],body:body.match(/name="body"\r\n\r\n([\s\S]*?)\r\n--/)?.[1]||'',sequence:++chat.revision,event_sequence:chat.revision,created_at:new Date().toISOString(),edited:false,deleted:false,reply:null,attachments:[],reactions:[]};
    rows[id].push(message);chat.last_message=message;return json(message,201);
   }
   return json({results:rows[id],cursor:chat.revision,has_more:false,before:null,conversation:chat});
  }
  if(path.endsWith('/read/')){chat.unread=0;return json({ok:true});}
  if(path.endsWith('/typing/'))return json({ok:true});return json(chat);
 });return {requests,family,system,rows};
}
