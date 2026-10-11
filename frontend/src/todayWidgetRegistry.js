export const TODAY_LAYOUT_VERSION=2;
export const TODAY_WIDGET_SIZES=['compact','medium','wide'];
export const LEGACY_SIZE_MAP={compact:'compact',square:'medium',full:'wide'};

const weekSettings={events:true,waste:true,holidays:true,special:true};
const tripSettings={show_wishes:false};
const deprecatedTodoIds=new Set(['tasks','routines']);

const entry=(id,defaultOrder,{component='external',category='family',supportedSizes=['compact','wide'],defaultSize='wide',settingsSchema=null,deepLink=null}={})=>{
 if(!supportedSizes.includes(defaultSize))throw new Error(`Unsupported default size ${defaultSize} for ${id}`);
 return {id,titleKey:id,category,component,defaultVisible:true,defaultOrder,defaultSize,supportedSizes,moduleGate:null,permissionGate:null,
 sensitivity:'family',refreshPolicy:'on-focus',emptyStatePolicy:'render',deepLink,settingsSchema};
};

export const TodayWidgetRegistry=[
 entry('week',0,{component:'WeekCompassWidget',category:'planning',settingsSchema:weekSettings}),
 entry('priority',1,{category:'planning'}),
 entry('trip',2,{category:'planning',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium',settingsSchema:tripSettings}),
 entry('next',3,{category:'planning',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium'}),
 entry('pinboard',4,{component:'PinboardTodayWidget',category:'collaboration',defaultSize:'compact'}),
 entry('weather',5,{category:'context',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium'}),
 entry('todo',6,{component:'TodayTodoWidget',category:'planning'}),
 entry('shopping',7,{category:'household',defaultSize:'compact'}),
 entry('waste',8,{category:'household',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium'}),
 entry('inbox',9,{category:'collaboration',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium'}),
 entry('birthdays',10,{supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium'}),
 entry('notes',11,{supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'medium'}),
 entry('loyalty',12,{category:'household',supportedSizes:TODAY_WIDGET_SIZES,defaultSize:'compact'}),
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

function migrateTodoWidgets(rows){
 const todo=rows.find(row=>row.id==='todo');
 if(todo)return rows.filter(row=>!deprecatedTodoIds.has(row.id));
 const legacy=rows.map((row,index)=>({row,index})).filter(({row})=>deprecatedTodoIds.has(row.id));
 if(!legacy.length)return rows;
 const visible=legacy.some(({row})=>row.visible===true);
 const tasks=legacy.find(({row})=>row.id==='tasks')?.row;
 const preferred=tasks&&['compact','wide'].includes(tasks.size)?tasks.size:(legacy.map(({row})=>row.size).find(size=>['compact','wide'].includes(size))||'wide');
 const first=Math.min(...legacy.map(({index})=>index));
 const cleaned=rows.filter(row=>!deprecatedTodoIds.has(row.id));
 const insertAt=rows.slice(0,first).filter(row=>!deprecatedTodoIds.has(row.id)).length;
 cleaned.splice(insertAt,0,{id:'todo',visible,size:preferred});
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
 const widgets=migrateTodoWidgets(rows);
 const seen=new Set(widgets.map(widget=>widget.id));
 if(!seen.has('week')){widgets.unshift({...cleanTodayWidget({id:'week',visible:legacyDefaults,size:defaultSizeFor('week')}),settings:settingsFor('week')});seen.add('week')}
 if(!seen.has('trip')){const index=widgets.findIndex(widget=>widget.id==='priority');widgets.splice(index>=0?index+1:Math.min(1,widgets.length),0,{...cleanTodayWidget({id:'trip',visible:legacyDefaults,size:defaultSizeFor('trip')}),settings:settingsFor('trip')});seen.add('trip')}
 if(!seen.has('pinboard')){const index=widgets.findIndex(widget=>widget.id==='next');widgets.splice(index>=0?index+1:Math.min(5,widgets.length),0,cleanTodayWidget({id:'pinboard',visible:legacyDefaults,size:defaultSizeFor('pinboard')}));seen.add('pinboard')}
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
