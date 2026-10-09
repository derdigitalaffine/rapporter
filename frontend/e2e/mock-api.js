const familyId='family-1';
const now=()=>Date.now();
const isoIn=hours=>new Date(now()+hours*3600000).toISOString();

function json(route,body,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}
function empty(route,status=204){return route.fulfill({status,body:''})}
function idFrom(path,prefix){return path.slice(prefix.length).split('/')[0]}

export async function installApiMocks(page,{authenticated=true,language='de',dismissOnboarding=true}={}){
  await page.addInitScript(({authenticated,language,dismissOnboarding,familyId})=>{
    if(authenticated)localStorage.setItem('famuhle-session','1');else localStorage.removeItem('famuhle-session');
    localStorage.setItem('famuhle-language',language);
    if(dismissOnboarding)localStorage.setItem(`famuhle-onboarding-dismissed:${familyId}`,'1');
  },{authenticated,language,dismissOnboarding,familyId});

  const state={
    family:{id:familyId,name:'Musterfamilie',slug:'musterfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[]},
    memberships:[
      {id:'member-1',family:familyId,user:1,username:'alex',role:'owner',display_name:'Alex',avatar:''},
      {id:'member-2',family:familyId,user:2,username:'sam',role:'adult',display_name:'Sam',avatar:''},
    ],
    taskLists:[{id:'tasks-1',family:familyId,name:'Alltag',icon:'list-check',archived:false,sort_order:0}],
    tasks:[{id:'task-1',family:familyId,task_list:'tasks-1',title:'Wäsche aufhängen',notes:'',priority:'normal',estimate_minutes:10,assignee:1,assignee_name:'Alex',list_name:'Alltag',due_at:isoIn(3),completed_at:null}],
    shoppingLists:[{id:'shop-1',family:familyId,name:'Supermarkt',store:'Markt',icon:'cart-shopping',archived:false,sort_order:0,items:[{id:'item-1',shopping_list:'shop-1',name:'Milch',quantity:'1 l',category:'Kühlung',aisle:'Kühlregal',note:'',favorite:true,checked:false,added_by_name:'Sam'}]}],
    routines:[],
    events:[
      {id:'event-past',family:familyId,source:null,type:'calendar.event',title:'Gestern erledigt',starts_at:isoIn(-30),ends_at:isoIn(-29),actionable:false,payload:{provider:'fam-uh-le',location:'Alt',description:'',recurrence:''}},
      {id:'event-1',family:familyId,source:null,type:'calendar.event',title:'Kinderarzt',starts_at:isoIn(5),ends_at:isoIn(6),actionable:false,payload:{provider:'fam-uh-le',location:'Praxis',description:'U-Heft mitnehmen',recurrence:''}},
    ],
    invitations:[],
    automationRules:[],
    integrations:[{id:'integration-1',family:familyId,name:'Open-Meteo',kind:'weather',enabled:true,endpoint:'',config:{adapter:'open_meteo'},last_sync_status:'error',last_sync_error:'Zeitüberschreitung beim Abruf',last_success_at:null,last_synced_at:null,next_sync_at:isoIn(1)}],
  };
  state.family.memberships=state.memberships;

  const taskLists=()=>state.taskLists.map(list=>({...list,open_count:state.tasks.filter(task=>task.task_list===list.id&&!task.completed_at).length,done_count:state.tasks.filter(task=>task.task_list===list.id&&task.completed_at).length}));
  const shoppingLists=()=>state.shoppingLists.map(list=>({...list,open_count:list.items.filter(item=>!item.checked).length,checked_count:list.items.filter(item=>item.checked).length}));
  const dashboard=()=>({tasks:state.tasks,task_lists:taskLists(),events:state.events,routines:state.routines,shopping_lists:shoppingLists(),inbox_count:0,automation_count:state.automationRules.filter(rule=>rule.enabled).length});

  await page.route('**/api/**',async route=>{
    const request=route.request();
    const method=request.method();
    const url=new URL(request.url());
    const path=url.pathname.replace(/^\/api/,'');
    let body={};try{body=request.postDataJSON()||{}}catch{}

    if(path==='/auth/login/'&&method==='POST')return json(route,{authenticated:true});
    if(path==='/auth/refresh/'&&method==='POST')return json(route,{authenticated:true});
    if(path==='/auth/logout/'&&method==='POST')return json(route,{authenticated:false});
    if(path==='/auth/session/'&&method==='GET')return json(route,{authenticated:true,user:{id:1,username:'alex',email:'alex@example.test'}});
    if(path==='/dashboard/'&&method==='GET')return json(route,dashboard());
    if(path==='/families/'&&method==='GET')return json(route,[state.family]);

    if(path==='/task-lists/'&&method==='GET')return json(route,taskLists());
    if(path==='/task-lists/'&&method==='POST'){
      const list={id:`tasks-${state.taskLists.length+1}`,family:body.family,name:body.name,icon:body.icon||'list-check',archived:false,sort_order:0};state.taskLists.push(list);return json(route,{...list,open_count:0,done_count:0},201);
    }
    if(path==='/tasks/suggestions/'&&method==='GET')return json(route,[]);
    if(path==='/tasks/'&&method==='GET')return json(route,state.tasks);
    if(path==='/smart/tasks/quick-add/'&&method==='POST'){
      const list=state.taskLists.find(item=>item.id===body.task_list)||state.taskLists[0];
      const task={id:`task-${state.tasks.length+1}`,family:body.family,task_list:list?.id||null,title:body.title,notes:body.notes||'',priority:body.priority||'normal',estimate_minutes:body.estimate_minutes||null,assignee:null,assignee_name:'',list_name:list?.name||'',due_at:null,completed_at:null};state.tasks.push(task);return json(route,task,201);
    }
    if(/^\/tasks\/[^/]+\/toggle\/$/.test(path)&&method==='POST'){
      const id=idFrom(path,'/tasks/');const task=state.tasks.find(item=>String(item.id)===String(id));if(task)task.completed_at=task.completed_at?null:new Date().toISOString();return json(route,task||{});
    }
    if(/^\/tasks\/[^/]+\/$/.test(path)){
      const id=idFrom(path,'/tasks/');const index=state.tasks.findIndex(item=>String(item.id)===String(id));
      if(method==='PATCH'){state.tasks[index]={...state.tasks[index],...body};const list=state.taskLists.find(item=>item.id===state.tasks[index].task_list);state.tasks[index].list_name=list?.name||'';return json(route,state.tasks[index])}
      if(method==='DELETE'){if(index>=0)state.tasks.splice(index,1);return empty(route)}
    }

    if(path==='/shopping-lists/'&&method==='GET')return json(route,shoppingLists());
    if(path==='/shopping-lists/'&&method==='POST'){
      const list={id:`shop-${state.shoppingLists.length+1}`,family:body.family,name:body.name,store:body.store||'',icon:body.icon||'cart-shopping',archived:false,sort_order:0,items:[]};state.shoppingLists.push(list);return json(route,{...list,open_count:0,checked_count:0},201);
    }
    if(path==='/shopping-items/suggestions/'&&method==='GET')return json(route,[]);
    if(path==='/smart/shopping/quick-add/'&&method==='POST'){
      const list=state.shoppingLists.find(item=>item.id===body.shopping_list)||state.shoppingLists[0];const item={id:`item-${list.items.length+1}`,shopping_list:list.id,name:body.name,quantity:body.quantity||'',category:body.category||'',aisle:body.aisle||'',note:body.note||'',favorite:false,checked:false,added_by_name:'Alex'};list.items.push(item);return json(route,item,201);
    }
    if(/^\/shopping-items\/[^/]+\/toggle\/$/.test(path)&&method==='POST'){
      const id=idFrom(path,'/shopping-items/');const item=state.shoppingLists.flatMap(list=>list.items).find(row=>String(row.id)===String(id));if(item)item.checked=!item.checked;return json(route,item||{});
    }
    if(/^\/shopping-items\/[^/]+\/$/.test(path)){
      const id=idFrom(path,'/shopping-items/');const list=state.shoppingLists.find(row=>row.items.some(item=>String(item.id)===String(id)));const index=list?.items.findIndex(item=>String(item.id)===String(id))??-1;
      if(method==='PATCH'&&index>=0){list.items[index]={...list.items[index],...body};return json(route,list.items[index])}
      if(method==='DELETE'&&index>=0){list.items.splice(index,1);return empty(route)}
    }
    if(/^\/smart\/shopping\/[^/]+\/favorite\/$/.test(path)&&method==='POST'){
      const id=idFrom(path,'/smart/shopping/');const item=state.shoppingLists.flatMap(list=>list.items).find(row=>String(row.id)===String(id));if(item)item.favorite=!item.favorite;return json(route,item||{});
    }
    if(/^\/smart\/shopping-lists\/[^/]+\/clear-checked\/$/.test(path)&&method==='POST'){
      const id=idFrom(path,'/smart/shopping-lists/');const list=state.shoppingLists.find(row=>String(row.id)===String(id));if(list)list.items=list.items.filter(item=>!item.checked);return json(route,{cleared:true});
    }

    if(path==='/events/'&&method==='GET')return json(route,state.events);
    if(path==='/events/'&&method==='POST'){
      const event={id:`event-${state.events.length+1}`,...body};state.events.push(event);return json(route,event,201);
    }
    if(/^\/events\/[^/]+\/$/.test(path)){
      const id=idFrom(path,'/events/');const index=state.events.findIndex(event=>String(event.id)===String(id));
      if(method==='PATCH'){state.events[index]={...state.events[index],...body};return json(route,state.events[index])}
      if(method==='DELETE'){if(index>=0)state.events.splice(index,1);return empty(route)}
    }

    if(path==='/memberships/'&&method==='GET')return json(route,state.memberships);
    if(/^\/memberships\/[^/]+\/$/.test(path)&&method==='PATCH'){
      const id=idFrom(path,'/memberships/');const index=state.memberships.findIndex(member=>String(member.id)===String(id));state.memberships[index]={...state.memberships[index],...body};state.family.memberships=state.memberships;return json(route,state.memberships[index]);
    }
    if(path==='/invitations/'&&method==='GET')return json(route,state.invitations);
    if(path==='/invitations/'&&method==='POST'){
      const invite={id:`invite-${state.invitations.length+1}`,family:familyId,family_name:state.family.name,token:`token-${state.invitations.length+1}`,role:body.role,email:body.email||'',display_name:body.display_name||'',expires_at:body.expires_at,accepted_at:null,revoked_at:null,active:true,created_at:new Date().toISOString()};state.invitations.unshift(invite);return json(route,invite,201);
    }
    if(/^\/invitations\/[^/]+\/$/.test(path)&&method==='DELETE'){
      const id=idFrom(path,'/invitations/');const invite=state.invitations.find(item=>String(item.id)===String(id));if(invite){invite.active=false;invite.revoked_at=new Date().toISOString()}return empty(route);
    }

    if(path==='/automation-rules/templates/'&&method==='GET')return json(route,[{id:'waste_evening',name:'Müll rausstellen',description:'Erinnert am Abend vor der Abholung.'},{id:'rain_laundry',name:'Wäsche bei Regen',description:'Warnt vor hoher Regenwahrscheinlichkeit.'}]);
    if(path==='/automation-rules/'&&method==='GET')return json(route,state.automationRules);
    if(path==='/automation-rules/'&&method==='POST'){
      const rule={id:`rule-${state.automationRules.length+1}`,...body,enabled:true,executions:[]};state.automationRules.push(rule);return json(route,rule,201);
    }
    if(path==='/automation-rules/from_template/'&&method==='POST'){
      const rule={id:`rule-${state.automationRules.length+1}`,family:familyId,name:'Müll rausstellen',trigger_type:'waste_tomorrow',action_type:'task_create',enabled:true,executions:[]};state.automationRules.push(rule);return json(route,rule,201);
    }
    if(/^\/automation-rules\/[^/]+\/toggle\/$/.test(path)&&method==='POST'){
      const id=idFrom(path,'/automation-rules/');const rule=state.automationRules.find(item=>String(item.id)===String(id));if(rule)rule.enabled=!rule.enabled;return json(route,rule||{});
    }
    if(/^\/automation-rules\/[^/]+\/run\/$/.test(path)&&method==='POST')return json(route,{status:'success'});
    if(/^\/automation-rules\/[^/]+\/$/.test(path)&&method==='DELETE'){
      const id=idFrom(path,'/automation-rules/');state.automationRules=state.automationRules.filter(item=>String(item.id)!==String(id));return empty(route);
    }

    if(path==='/integrations/'&&method==='GET')return json(route,state.integrations);
    if(path==='/integration-hub/catalog/'&&method==='GET')return json(route,[
      {id:'open_meteo',name:'Open-Meteo',description:'Wettervorhersage für eure Familie.',kind:'weather',defaults:{adapter:'open_meteo'},fields:[{key:'latitude',label:'Breitengrad',type:'number',required:true},{key:'longitude',label:'Längengrad',type:'number',required:true}]},
      {id:'waste_ics',name:'Abfallkalender',description:'Offiziellen ICS-Kalender verbinden.',kind:'waste',defaults:{adapter:'ics'},fields:[{key:'url',label:'ICS-Link',type:'url',required:true}]},
    ]);
    if(/^\/integration-hub\/[^/]+\/sync\/$/.test(path)&&method==='POST'){
      const id=idFrom(path,'/integration-hub/');const integration=state.integrations.find(item=>String(item.id)===String(id));if(integration){integration.last_sync_status='success';integration.last_sync_error='';integration.last_success_at=new Date().toISOString()}return json(route,{synced:3});
    }
    if(path==='/integration-hub/sync-all/'&&method==='POST')return json(route,{synced:3,errors:[]});

    if(path==='/routines/'&&method==='GET')return json(route,state.routines);
    if(path==='/inbox/'&&method==='GET')return json(route,[]);
    if(path==='/push/config/'&&method==='GET')return json(route,{configured:false,subscriptions:0});
    if(method==='GET')return json(route,[]);
    return json(route,{});
  });

  return state;
}