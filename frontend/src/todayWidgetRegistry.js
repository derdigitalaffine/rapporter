export const TODAY_LAYOUT_VERSION=2;
export const TODAY_WIDGET_SIZES=['compact','medium','wide'];
export const LEGACY_SIZE_MAP={compact:'compact',square:'medium',full:'wide'};

const weekSettings={events:true,waste:true,holidays:true,special:true};
const tripSettings={show_wishes:false};
const deprecatedTodoIds=new Set(['tasks','routines']);
const legacyCoreAliases={priority:'focus',next:'timeline'};

const entry=(id,defaultOrder,{component='external',category='family',supportedSizes=['compact','wide'],defaultSize='wide',defaultVisible=true,settingsSchema=null,deepLink=null}={})=>{
 if(!supportedSizes.includes(defaultSize))throw new Error(`Unsupported default size ${defaultSize} for ${id}`);
 return {id,titleKey:id,category,component,defaultVisible,defaultOrder,defaultSize,supportedSizes,moduleGate:null,permissionGate:null,
 sensitivity:'family',refreshPolicy:'on-focus',emptyStatePolicy:'render',deepLink,settingsSchema};
};

export const TodayWidgetRegistry=[
 entry('focus',0,{component:'TodayFocusWidget',category:'planning',defaultSize:'wide'}),
 entry('timeline',1,{component:'TodayTimelineWidget',category:'planning',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'wide'}),
 entry('week',2,{component:'WeekCompassWidget',category:'planning',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium',settingsSchema:weekSettings}),
 entry('todo',3,{component:'TodayTodoWidget',category:'planning',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'compact'}),
 entry('pinboard',4,{component:'PinboardTodayWidget',category:'collaboration',defaultSize:'compact'}),
 entry('tomorrow',5,{component:'TodayTomorrowWidget',category:'planning',supportedSizes:['compact','medium'],defaultSize:'compact',defaultVisible:false}),
 entry('family-load',6,{component:'TodayFamilyLoadWidget',category:'family',supportedSizes:['compact','medium'],defaultSize:'compact',defaultVisible:false}),
 entry('trip',7,{category:'planning',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium',defaultVisible:false,settingsSchema:tripSettings}),
 entry('weather',8,{category:'context',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium',defaultVisible:false}),
 entry('shopping',9,{category:'household',defaultSize:'compact',defaultVisible:false}),
 entry('waste',10,{category:'household',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium',defaultVisible:false}),
 entry('inbox',11,{category:'collaboration',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium',defaultVisible:false}),
 entry('birthdays',12,{supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium',defaultVisible:false}),
 entry('notes',13,{supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium',defaultVisible:false}),
 entry('loyalty',14,{category:'household',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'compact',defaultVisible:false}),
];

export const TodayWidgetsById=Object.fromEntries(TodayWidgetRegistry.map(widget=>[widget.id,widget]));
const safeId=/^[a-z][a-z0-9_-]{0,63}$/;

export const settingsFor=id=>{
 const schema=TodayWidgetsById[id]?.settingsSchema;
 return schema?{...schema}:null;
};

export const sizeOptionsFor=id=>TodayWidgetsById[id]?.supportedSizes||TODAY_WIDGET_SIZES;
const defaultSizeFor=id=>TodayWidgetsById[id]?.defaultSize||'wide';

export const defaultTodayWidgets=()=>TodayWidgetRegistry
 .slice().sort((a,b)=>a.defaultOrder-b.defaultOrder)
 .map(widget=>({id:widget.id,visible:widget.defaultVisible,size:widget.defaultSize,...(settingsFor(widget.id)?{settings:settingsFor(widget.id)}:{})}));

export const cleanTodayWidget=widget=>{
 const settings=settingsFor(widget.id);
 const row={id:widget.id,visible:widget.visible,size:widget.size};
 if(settings)row.settings={...settings,...(widget.settings||{})};
 return row;
};

function migrateCoreWidgets(rows){
 const canonical=new Set(rows.filter(row=>!legacyCoreAliases[row.id]).map(row=>row.id));
 const migrated=[];
 rows.forEach(row=>{
  const target=legacyCoreAliases[row.id];
  if(!target){migrated.push(row);return}
  if(canonical.has(target))return;
  const definition=TodayWidgetsById[target];
  migrated.push({...row,id:target,size:definition.supportedSizes.includes(row.size)?row.size:definition.defaultSize});
  canonical.add(target);
 });
 return migrated;
}

function migrateTodoWidgets(rows){
 const todo=rows.find(row=>row.id==='todo');
 if(todo)return rows.filter(row=>!deprecatedTodoIds.has(row.id));
 const legacy=rows.map((row,index)=>({row,index})).filter(({row})=>deprecatedTodoIds.has(row.id));
 if(!legacy.length)return rows;
 const visible=legacy.some(({row})=>row.visible===true);
 const tasks=legacy.find(({row})=>row.id==='tasks')?.row;
 const preferred=tasks&&TODAY_WIDGET_SIZES.includes(tasks.size)?tasks.size:(legacy.map(({row})=>row.size).find(size=>TODAY_WIDGET_SIZES.includes(size))||defaultSizeFor('todo'));
 const first=Math.min(...legacy.map(({index})=>index));
 const cleaned=rows.filter(row=>!deprecatedTodoIds.has(row.id));
 const insertAt=rows.slice(0,first).filter(row=>!deprecatedTodoIds.has(row.id)).length;
 cleaned.splice(insertAt,0,{id:'todo',visible,size:TodayWidgetsById.todo.supportedSizes.includes(preferred)?preferred:defaultSizeFor('todo')});
 return cleaned;
}

function normalizeRow(raw,version){
 if(!raw||typeof raw!=='object'||Array.isArray(raw)||typeof raw.id!=='string'||!safeId.test(raw.id)||typeof raw.visible!=='boolean')return null;
 let size=raw.size;
 if(version===1)size=LEGACY_SIZE_MAP[size];
 if(!TODAY_WIDGET_SIZES.includes(size))return null;
 const entry=TodayWidgetsById[raw.id];
 if(entry&&!entry.supportedSizes.includes(size))return null;
 if(raw.id==='tasks'&&!['compact','wide'].includes(size))return null;
 if(raw.id==='routines'&&!TODAY_WIDGET_SIZES.includes(size))return null;
 const defaults=settingsFor(raw.id);
 const allowed=defaults?['id','visible','size','settings']:['id','visible','size'];
 if(Object.keys(raw).some(key=>!allowed.includes(key)))return null;
 const row={id:raw.id,visible:raw.visible,size};
 if(defaults){
  const supplied=raw.settings;
  if(supplied!==undefined&&(!supplied||typeof supplied!=='object'||Array.isArray(supplied)||Object.keys(supplied).length!==Object.keys(defaults).length||Object.keys(defaults).some(key=>typeof supplied[key]!=='boolean')))return null;
  row.settings={...defaults,...(supplied||{})};
 }
 return row;
}

function expandKnownWidgets(rows,legacyDefaults){
 const widgets=migrateTodoWidgets(migrateCoreWidgets(rows));
 const seen=new Set(widgets.map(widget=>widget.id));
 if(!seen.has('week')){const timelineIndex=widgets.findIndex(widget=>widget.id==='timeline');widgets.splice(timelineIndex>=0?timelineIndex+1:0,0,{...cleanTodayWidget({id:'week',visible:legacyDefaults,size:defaultSizeFor('week')}),settings:settingsFor('week')});seen.add('week')}
 if(!seen.has('trip')){const focusIndex=widgets.findIndex(widget=>widget.id==='focus');widgets.splice(focusIndex>=0?focusIndex+1:Math.min(1,widgets.length),0,{...cleanTodayWidget({id:'trip',visible:legacyDefaults,size:defaultSizeFor('trip')}),settings:settingsFor('trip')});seen.add('trip')}
 if(!seen.has('pinboard')){const timelineIndex=widgets.findIndex(widget=>widget.id==='timeline');widgets.splice(timelineIndex>=0?timelineIndex+1:Math.min(5,widgets.length),0,cleanTodayWidget({id:'pinboard',visible:legacyDefaults,size:defaultSizeFor('pinboard')}));seen.add('pinboard')}
 TodayWidgetRegistry.forEach(entry=>{if(!seen.has(entry.id)){widgets.push(cleanTodayWidget({id:entry.id,visible:false,size:entry.defaultSize}));seen.add(entry.id)}});
 return widgets;
}

export function normalizeTodayLayout(value){
 if(!value||![1,TODAY_LAYOUT_VERSION].includes(value.version)||!Number.isInteger(value.revision)||value.revision<0||!Array.isArray(value.widgets)||value.widgets.length>64)return null;
 const rows=[];const seen=new Set();
 for(const raw of value.widgets){
  const row=normalizeRow(raw,value.version);
  if(!row||seen.has(row.id)||(value.version===TODAY_LAYOUT_VERSION&&deprecatedTodoIds.has(row.id)))return null;
  seen.add(row.id);rows.push(row);
 }
 return {version:TODAY_LAYOUT_VERSION,revision:value.revision,widgets:expandKnownWidgets(rows,value.version===1)};
}
