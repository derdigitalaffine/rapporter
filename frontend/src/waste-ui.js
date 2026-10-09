const RULES={
 rest:['restmüll','restmuell','restmull','restabfall','restafall','hausmüll','hausmuell','hausmull','graue tonne','schwarze tonne','residual waste'],
 yellow:['gelbe tonne','gelber sack','gelbe säcke','gelbe saecke','leichtverpack','verpackungsabfall','wertstoff',' lvp ','yellow bin'],
 bio:['biomüll','biomuell','biomull','bioabfall','biotonne','braune tonne','kompost','organic waste'],
 paper:['altpapier','papiertonne','blaue tonne','papier','pappe','karton','paper'],
};

function normalize(value=''){
 return ` ${String(value).toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/ß/g,'ss').replace(/[^a-z0-9äöü]+/g,' ')} `;
}

export function wasteKinds(event){
 const payload=event?.payload||{};
 const stored=Array.isArray(payload.waste_kinds)?payload.waste_kinds.filter(Boolean):[];
 if(stored.length)return stored;
 if(payload.waste_kind&&payload.waste_kind!=='unknown')return [payload.waste_kind];
 const text=normalize(`${event?.title||''} ${payload.description||''}`);
 const matches=[];
 Object.entries(RULES).forEach(([kind,phrases])=>{
   const positions=phrases.map(phrase=>text.indexOf(normalize(phrase).trim())).filter(index=>index>=0);
   if(positions.length)matches.push([Math.min(...positions),kind]);
 });
 return matches.sort((a,b)=>a[0]-b[0]).map(([,kind])=>kind);
}

export function wasteKind(event){return wasteKinds(event)[0]||'unknown'}
export function wasteClass(event){return `waste-${wasteKind(event)}`}
export function isWasteEvent(event){return String(event?.type||'').includes('waste')}

export function wasteKindLabel(kind,language='de'){
 const de={rest:'Restmüll',yellow:'Gelbe Tonne',bio:'Biomüll',paper:'Papier',unknown:'Müllabfuhr'};
 const en={rest:'Residual waste',yellow:'Yellow bin',bio:'Organic waste',paper:'Paper',unknown:'Waste collection'};
 return (String(language).startsWith('de')?de:en)[kind]||(String(language).startsWith('de')?de.unknown:en.unknown);
}
