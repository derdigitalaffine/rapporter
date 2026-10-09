const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});
const noContent=route=>route.fulfill({status:204,body:''});
const idFrom=(pathname,prefix)=>Number(pathname.slice(prefix.length).split('/')[0]);

export async function installMockApi(page,{integrationMode='empty'}={}){
  const state={
    family:{id:1,name:'Testfamilie',timezone:'Europe/Berlin',memberships:[
      {id:1,family:1,user:1,username:'mama',display_name:'Mama',role:'owner'},
      {id:2,family:1,user:2,username:'papa',display_name:'Papa',role:'adult'},
    ]},
    taskLists:[{id:11,family:1,name:'Familie',icon:'list-check',archived:false,open_count:1}],
    tasks:[{id:101,family:1,task_list:11,list_name:'Familie',title:'Müll rausbringen',notes:'',due_at:null,priority:'normal',estimate_minutes:null,assignee:null,assignee_name:'',completed_at:null}],
    shoppingLists:[{id:21,family:1,name:'Einkauf',store:'REWE',icon:'cart-shopping',archived:false,open_count:1,items:[{id:201,shopping_list:21,name:'Milch',quantity:'1 l',category:'Kühlung',aisle:'Kühlregal',note:'',favorite:false,checked:false,added_by_name:'Mama'}]}],
    events:[{id:301,family:1,type:'calendar.event',title:'Elternabend',starts_at:new Date(Date.now()+86400000).toISOString(),ends_at:new Date(Date.now()+90000000).toISOString(),source:null,payload:{provider:'fam-uh-le',location:'Schule',description:'',recurrence:''}}],
    routines:[{id:401,family:1,name:'Bettwäsche wechseln',suggested_interval_days:14,last_done_at:null,active:true,icon:'history'}],
    memberships:[],
    invitations:[],
    rules:[{id:501,family:1,name:'Müll erinnern',trigger_type:'waste_tomorrow',action_type:'task_create',enabled:true,trigger_config:{},action_config:{title:'Müll rausstellen'},executions:[]}],
    templates:[{id:'waste_reminder',name:'Müll erinnern',description:'Erinnert vor der Müllabfuhr.'},{id:'frost_warning',name:'Frostschutz',description:'Warnt bei Frost.'}],
    integrations:integrationMode==='connected'?[{id:601,family:1,name:'Wetter',kind:'weather',enabled:true,config:{adapter:'open_meteo'},last_sync_status:'success',last_success_at:new Date().toISOString()}]:integrationMode==='error'?[{id:602,family:1,name:'Kalender mit Fehler',kind:'ics',enabled:true,config:{adapter:'ics'},last_sync_status:'error',last_sync_error:'Quelle nicht erreichbar',next_sync_at:new Date(Date.now()+600000).toISOString()}]:[],
  };
  state.memberships=state.family.memberships;

  const refreshCounts=()=>{
    state.taskLists.forEach(list=>list.open_count=state.tasks.filter(task=>task.task_list===list.id&&!task.completed_at).length);
    state.shoppingLists.forEach(list=>list.open_count=(list.items||[]).filter(item=>!item.checked).length);
  };
  const dashboard=()=>({tasks:state.tasks,task_lists:state.taskLists,events:state.events,routines:state.routines,shopping_lists:state.shoppingLists,inbox_count:0,automation_count:state.rules.filter(rule=>rule.enabled).length});
  const bodyOf=request=>{try{return request.postDataJSON()||{}}catch{return{}}};

  await page.route('**/api/**',async route=>{
    const request=route.request();const url=new URL(request.url());const p=url.pathname.replace(/^\/api/,'');const method=request.method();const body=bodyOf(request);
    refreshCounts();

    if(p==='/auth/login/'&&method==='POST')return json(route,{ok:true});
    if(p==='/auth/session/'&&method==='GET')return json(route,{authenticated:true});
    if(p==='/auth/refresh/'&&method==='POST')return json(route,{ok:true});
    if(p==='/auth/logout/'&&method==='POST')return noContent(route);
    if(p==='/dashboard/'&&method==='GET')return json(route,dashboard());
    if(p==='/families/'&&method==='GET')return json(route,[state.family]);

    if(p==='/task-lists/'&&method==='GET')return json(route,state.taskLists);
    if(p==='/task-lists/'&&method==='POST'){const row={id:Date.now(),family:body.family,name:body.name,icon:body.icon||'list-check',archived:false,open_count:0};state.taskLists.push(row);return json(route,row,201)}
    if(p.startsWith('/task-lists/')&&method==='PATCH'){const id=idFrom(p,'/task-lists/');const row=state.taskLists.find(x=>x.id===id);Object.assign(row,body);return json(route,row)}
    if(p==='/tasks/'&&method==='GET')return json(route,state.tasks);
    if(p==='/tasks/suggestions/'&&method==='GET')return json(route,[]);
    if(p==='/smart/tasks/quick-add/'&&method==='POST'){const list=state.taskLists.find(x=>x.id===Number(body.task_list))||state.taskLists[0];const row={id:Date.now(),family:body.family,task_list:list?.id||null,list_name:list?.name||'',title:body.title,notes:body.notes||'',due_at:null,priority:body.priority||'normal',estimate_minutes:body.estimate_minutes||null,assignee:null,assignee_name:'',completed_at:null};state.tasks.push(row);return json(route,row,201)}
    if(/^\/tasks\/\d+\/toggle\/$/.test(p)&&method==='POST'){const id=idFrom(p,'/tasks/');const row=state.tasks.find(x=>x.id===id);row.completed_at=row.completed_at?null:new Date().toISOString();return json(route,row)}
    if(/^\/tasks\/\d+\/$/.test(p)&&method==='PATCH'){const id=idFrom(p,'/tasks/');const row=state.tasks.find(x=>x.id===id);Object.assign(row,body);const list=state.taskLists.find(x=>x.id===Number(row.task_list));row.list_name=list?.name||'';return json(route,row)}
    if(/^\/tasks\/\d+\/$/.test(p)&&method==='DELETE'){const id=idFrom(p,'/tasks/');state.tasks=state.tasks.filter(x=>x.id!==id);return noContent(route)}

    if(p==='/shopping-lists/'&&method==='GET')return json(route,state.shoppingLists);
    if(p==='/shopping-lists/'&&method==='POST'){const row={id:Date.now(),family:body.family,name:body.name,store:body.store||'',icon:body.icon||'cart-shopping',archived:false,open_count:0,items:[]};state.shoppingLists.push(row);return json(route,row,201)}
    if(/^\/shopping-lists\/\d+\/$/.test(p)&&method==='PATCH'){const id=idFrom(p,'/shopping-lists/');const row=state.shoppingLists.find(x=>x.id===id);Object.assign(row,body);return json(route,row)}
    if(p==='/shopping-items/suggestions/'&&method==='GET')return json(route,[]);
    if(p==='/smart/shopping/quick-add/'&&method==='POST'){const list=state.shoppingLists.find(x=>x.id===Number(body.shopping_list))||state.shoppingLists[0];const row={id:Date.now(),shopping_list:list.id,name:body.name,quantity:body.quantity||'',category:body.category||'',aisle:body.aisle||'',note:body.note||'',favorite:false,checked:false,added_by_name:'Mama'};list.items.push(row);return json(route,row,201)}
    if(/^\/shopping-items\/\d+\/toggle\/$/.test(p)&&method==='POST'){const id=idFrom(p,'/shopping-items/');const row=state.shoppingLists.flatMap(x=>x.items).find(x=>x.id===id);row.checked=!row.checked;return json(route,row)}
    if(/^\/shopping-items\/\d+\/$/.test(p)&&method==='PATCH'){const id=idFrom(p,'/shopping-items/');const row=state.shoppingLists.flatMap(x=>x.items).find(x=>x.id===id);Object.assign(row,body);return json(route,row)}
    if(/^\/shopping-items\/\d+\/$/.test(p)&&method==='DELETE'){const id=idFrom(p,'/shopping-items/');state.shoppingLists.forEach(list=>list.items=list.items.filter(x=>x.id!==id));return noContent(route)}
    if(/^\/smart\/shopping\/\d+\/favorite\/$/.test(p)&&method==='POST'){const id=idFrom(p,'/smart/shopping/');const row=state.shoppingLists.flatMap(x=>x.items).find(x=>x.id===id);row.favorite=!row.favorite;return json(route,row)}
    if(/^\/smart\/shopping-lists\/\d+\/clear-checked\/$/.test(p)&&method==='POST'){const id=idFrom(p,'/smart/shopping-lists/');const list=state.shoppingLists.find(x=>x.id===id);list.items=list.items.filter(x=>!x.checked);return json(route,{removed:true})}

    if(p==='/events/'&&method==='GET')return json(route,state.events);
    if(p==='/events/'&&method==='POST'){const row={id:Date.now(),source:null,...body};state.events.push(row);return json(route,row,201)}
    if(/^\/events\/\d+\/$/.test(p)&&method==='PATCH'){const id=idFrom(p,'/events/');const row=state.events.find(x=>x.id===id);Object.assign(row,body);return json(route,row)}
    if(/^\/events\/\d+\/$/.test(p)&&method==='DELETE'){const id=idFrom(p,'/events/');state.events=state.events.filter(x=>x.id!==id);return noContent(route)}

    if(p==='/memberships/'&&method==='GET')return json(route,state.memberships);
    if(/^\/memberships\/\d+\/$/.test(p)&&method==='PATCH'){const id=idFrom(p,'/memberships/');const row=state.memberships.find(x=>x.id===id);Object.assign(row,body);return json(route,row)}
    if(/^\/memberships\/\d+\/$/.test(p)&&method==='DELETE'){const id=idFrom(p,'/memberships/');state.memberships=state.memberships.filter(x=>x.id!==id);state.family.memberships=state.memberships;return noContent(route)}
    if(p==='/invitations/'&&method==='GET')return json(route,state.invitations);
    if(p==='/invitations/'&&method==='POST'){const row={id:Date.now(),token:'e2e-invite-token',active:true,accepted_at:null,revoked_at:null,...body};state.invitations.push(row);return json(route,row,201)}
    if(/^\/invitations\/\d+\/$/.test(p)&&method==='DELETE'){const id=idFrom(p,'/invitations/');const row=state.invitations.find(x=>x.id===id);if(row){row.active=false;row.revoked_at=new Date().toISOString()}return noContent(route)}

    if(p==='/automation-rules/'&&method==='GET')return json(route,state.rules);
    if(p==='/automation-rules/templates/'&&method==='GET')return json(route,state.templates);
    if(p==='/automation-rules/'&&method==='POST'){const row={id:Date.now(),enabled:true,executions:[],...body};state.rules.push(row);return json(route,row,201)}
    if(p==='/automation-rules/from_template/'&&method==='POST'){const row={id:Date.now(),family:1,name:'Vorlage',trigger_type:'waste_tomorrow',action_type:'task_create',enabled:true,trigger_config:{},action_config:{title:'Müll rausstellen'},executions:[]};state.rules.push(row);return json(route,row,201)}
    if(/^\/automation-rules\/\d+\/toggle\/$/.test(p)&&method==='POST'){const id=idFrom(p,'/automation-rules/');const row=state.rules.find(x=>x.id===id);row.enabled=!row.enabled;return json(route,row)}
    if(/^\/automation-rules\/\d+\/run\/$/.test(p)&&method==='POST')return json(route,{executed:true});
    if(/^\/automation-rules\/\d+\/$/.test(p)&&method==='DELETE'){const id=idFrom(p,'/automation-rules/');state.rules=state.rules.filter(x=>x.id!==id);return noContent(route)}

    if(p==='/integrations/'&&method==='GET')return json(route,state.integrations);
    if(p==='/integration-hub/catalog/'&&method==='GET')return json(route,[{id:'open_meteo',kind:'weather',name:'Open-Meteo',description:'Wettervorhersage',defaults:{adapter:'open_meteo'},fields:[]}]);
    if(/^\/integration-hub\/\d+\/sync\/$/.test(p)&&method==='POST'){if(integrationMode==='error')return json(route,{detail:'Quelle nicht erreichbar'},500);return json(route,{synced:3})}
    if(p==='/integration-hub/sync-all/'&&method==='POST')return json(route,{synced:3,errors:integrationMode==='error'?['Quelle nicht erreichbar']:[]});
    if(p==='/integration-hub/connect/'&&method==='POST')return json(route,{connected:true},201);

    if(p==='/inbox/'&&method==='GET')return json(route,[]);
    if(p==='/push/config/'&&method==='GET')return json(route,{configured:false,devices:0,public_key:''});

    return json(route,{detail:`Unhandled E2E API route: ${method} ${p}`},500);
  });
  return state;
}

export async function authenticate(page,language='de'){
  await page.addInitScript(lang=>{localStorage.setItem('famuhle-session','1');localStorage.setItem('famuhle-language',lang)},language);
}
