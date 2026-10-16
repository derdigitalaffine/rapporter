import {useEffect,useMemo,useRef,useState} from 'react';
import {api,AUTH_CHANGED_EVENT} from './api';
import FileDropZone from './FileDropZone';
import {FieldGroup,FormActions,FormField,FormShell} from './form-primitives';
import EntityPicker from './ui/FamilyCombobox';
import {Icon} from './icons';
import {pinIconName,pinTypeLabel} from './pinboard-ui';
import {pinComposerCopy} from './pin-composer-copy';
import {PIN_TYPES_UPDATED_EVENT,pinTypeScopeKey,pinTypeStorageKey,readPinTypePreferences,writePinTypePreferences} from './pin-type-preferences';
import './pin-composer.css';

const ADAPTERS={
 task:{kind:'task',icon:'tasks',labelKey:'task'},
 routine:{kind:'routine',icon:'history',labelKey:'routine'},
 calendar_event:{kind:'event',icon:'calendar',labelKey:'calendar_event'},
 shopping_item:{kind:'shopping',icon:'shopping',labelKey:'shopping_item'},
 shopping_list:{kind:'shopping_list',icon:'shopping',labelKey:'shopping_list'},
 document:{kind:'document',icon:'lists',labelKey:'document'},
 note:{kind:'note_ref',icon:'lists',labelKey:'note_ref'},
 trip:{kind:'trip',icon:'route',labelKey:'trip'},
};
const GROUPS=[
 {key:'todos',adapters:['task','routine']},
 {key:'calendar',adapters:['calendar_event']},
 {key:'shopping',adapters:['shopping_item','shopping_list']},
 {key:'documents',adapters:['document']},
 {key:'more',adapters:['note','trip']},
];
const KIND_TO_ADAPTER=Object.fromEntries(Object.entries(ADAPTERS).map(([key,value])=>[value.kind,key]));
const itemLabel=item=>[item?.title,item?.subtitle].filter(Boolean).join(' · ');

export default function PinComposer({
 familyId,
 preferenceScope=null,
 language='de',
 kind,
 setKind,
 adapterKey,
 setAdapterKey,
 text,
 setText,
 files,
 addFiles,
 setFiles,
 targetId,
 setTargetId,
 editing,
 busy,
 onSubmit,
 onClose,
 removePhoto,
 members,
 visibility,
 setVisibility,
 selectedMembershipIds,
 setSelectedMembershipIds,
}){
 const w=pinComposerCopy(language);
 const initialAdapter=adapterKey||KIND_TO_ADAPTER[kind]||'task';
 const initialMode=editing?(editing.kind==='note'?'note':editing.kind==='photo'?'photo':'existing'):(kind==='photo'?'photo':KIND_TO_ADAPTER[kind]?'existing':'note');
 const [mode,setMode]=useState(initialMode);
 const [group,setGroup]=useState(GROUPS.find(row=>row.adapters.includes(initialAdapter))?.key||'todos');
 const [activeAdapter,setActiveAdapter]=useState(initialAdapter);
 const [query,setQuery]=useState('');
 const [items,setItems]=useState([]);
 const [hasNext,setHasNext]=useState(false);
 const [page,setPage]=useState(1);
 const [pickerBusy,setPickerBusy]=useState(false);
 const [pickerError,setPickerError]=useState('');
 const [retryNonce,setRetryNonce]=useState(0);
 const generation=useRef(0);
 const alive=useRef(true);
 const scopeKey=pinTypeScopeKey(preferenceScope);
 const [hintsAuthorized,setHintsAuthorized]=useState(true);
 const [preferenceView,setPreferenceView]=useState(()=>({scopeKey,preferences:readPinTypePreferences(preferenceScope)}));
 const preferences=hintsAuthorized&&scopeKey&&preferenceView.scopeKey===scopeKey?preferenceView.preferences:{enabled:false,types:[]};
 useEffect(()=>{
  const refresh=()=>setPreferenceView({scopeKey,preferences:readPinTypePreferences(preferenceScope)});
  refresh();
  const changed=event=>{if(event.detail?.scopeKey===scopeKey)refresh()};
  const stored=event=>{if(event.key===null||event.key===pinTypeStorageKey(preferenceScope))refresh()};
  window.addEventListener(PIN_TYPES_UPDATED_EVENT,changed);window.addEventListener('storage',stored);
  return()=>{window.removeEventListener(PIN_TYPES_UPDATED_EVENT,changed);window.removeEventListener('storage',stored)};
 },[scopeKey]);

 const selected=useMemo(()=>items.find(item=>String(item.id)===String(targetId))||null,[items,targetId]);
 const isReference=editing?!['note','photo'].includes(editing.kind):mode==='existing';
 const contentValid=editing
  ?(!['note','photo'].includes(editing.kind)||Boolean(text.trim()||editing.images?.length))
  :mode==='photo'?files.length>0:mode==='note'?Boolean(text.trim()):Boolean(targetId);
 const valid=contentValid&&((isReference&&!editing)||visibility!=='selected'||selectedMembershipIds.length>0);

 useEffect(()=>()=>{alive.current=false;generation.current+=1},[]);
 useEffect(()=>{
  generation.current+=1;
  setItems([]);setHasNext(false);setPage(1);setPickerError('');setQuery('');setTargetId('');
 },[familyId,setTargetId]);
 useEffect(()=>{
  const onAuth=event=>{
   if(event.detail?.authenticated===false){generation.current+=1;setItems([]);setHasNext(false);setPickerError('');setTargetId('');setHintsAuthorized(false)}
  };
  window.addEventListener(AUTH_CHANGED_EVENT,onAuth);
  return()=>window.removeEventListener(AUTH_CHANGED_EVENT,onAuth);
 },[setTargetId]);

 useEffect(()=>{
  if(editing||mode!=='existing'||!familyId)return;
  const expected=ADAPTERS[activeAdapter];
  if(!expected)return;
  const request=++generation.current;
  setItems([]);setHasNext(false);setPage(1);setPickerError('');setPickerBusy(true);setTargetId('');
  setKind(expected.kind);setAdapterKey(activeAdapter);
  const timer=setTimeout(async()=>{
   try{
    const params=new URLSearchParams({family:String(familyId),adapter_key:activeAdapter,page:'1',page_size:'20'});
    if(query.trim())params.set('q',query.trim());
    const data=await api(`/board/picker/?${params}`);
    if(!alive.current||generation.current!==request)return;
    if(data?.adapter_key!==activeAdapter||data?.kind!==expected.kind)throw new Error(w.loadFailed);
    setItems(data.results||[]);setHasNext(Boolean(data.has_next));setPage(Number(data.page)||1);
   }catch(error){if(alive.current&&generation.current===request)setPickerError(error?.message||w.loadFailed)}
   finally{if(alive.current&&generation.current===request)setPickerBusy(false)}
  },query?180:0);
  return()=>clearTimeout(timer);
 },[activeAdapter,editing,familyId,mode,query,retryNonce,setAdapterKey,setKind,setTargetId,w.loadFailed]);

 function chooseMode(next){
  if(next===mode)return;
  generation.current+=1;setMode(next);setQuery('');setItems([]);setHasNext(false);setPage(1);setPickerError('');setTargetId('');setText('');setFiles([]);
  if(next==='existing'){
   const nextAdapter=GROUPS.find(row=>row.key===group)?.adapters[0]||'task';
   setActiveAdapter(nextAdapter);setAdapterKey(nextAdapter);setKind(ADAPTERS[nextAdapter].kind);
  }else{setAdapterKey('');setKind(next==='photo'?'photo':'note')}
 }
 function chooseGroup(nextGroup){
  const row=GROUPS.find(item=>item.key===nextGroup);if(!row)return;
  generation.current+=1;setGroup(nextGroup);setActiveAdapter(row.adapters[0]);setQuery('');setItems([]);setTargetId('');setAdapterKey(row.adapters[0]);setKind(ADAPTERS[row.adapters[0]].kind);setRetryNonce(value=>value+1);
 }
 function chooseAdapter(nextAdapter){
  if(!ADAPTERS[nextAdapter]||nextAdapter===activeAdapter)return;
  generation.current+=1;setActiveAdapter(nextAdapter);setQuery('');setItems([]);setTargetId('');setAdapterKey(nextAdapter);setKind(ADAPTERS[nextAdapter].kind);
 }
 function changeQuery(value){generation.current+=1;setTargetId('');setQuery(value)}
 function changeSelection(ids){setTargetId(ids[0]?String(ids[0]):'')}
 function chooseRecentType(key){
  const row=GROUPS.find(group=>group.adapters.includes(key));if(!row)return;
  generation.current+=1;setGroup(row.key);setActiveAdapter(key);setQuery('');setItems([]);setHasNext(false);setPickerError('');setTargetId('');setAdapterKey(key);setKind(ADAPTERS[key].kind);setRetryNonce(value=>value+1);
 }
 function changeTypeSuggestions(enabled){
  if(!hintsAuthorized||!scopeKey)return;
  setPreferenceView({scopeKey,preferences:writePinTypePreferences(preferenceScope,{enabled,types:enabled?preferences.types:[]})});
 }
 async function loadMore(){
  if(!hasNext||pickerBusy||pickerError||mode!=='existing')return;
  const expected=ADAPTERS[activeAdapter];const request=generation.current;const nextPage=page+1;setPickerBusy(true);
  try{
   const params=new URLSearchParams({family:String(familyId),adapter_key:activeAdapter,page:String(nextPage),page_size:'20'});if(query.trim())params.set('q',query.trim());
   const data=await api(`/board/picker/?${params}`);
   if(!alive.current||generation.current!==request)return;
   if(data?.adapter_key!==activeAdapter||data?.kind!==expected.kind)throw new Error(w.loadFailed);
   setItems(current=>{const seen=new Set(current.map(item=>String(item.id)));return [...current,...(data.results||[]).filter(item=>!seen.has(String(item.id)))]});
   setHasNext(Boolean(data.has_next));setPage(Number(data.page)||nextPage);
  }catch(error){if(alive.current&&generation.current===request)setPickerError(error?.message||w.loadFailed)}
  finally{if(alive.current&&generation.current===request)setPickerBusy(false)}
 }
 function retryPicker(){setPickerError('');setRetryNonce(value=>value+1)}

 const currentGroup=GROUPS.find(row=>row.key===group)||GROUPS[0];
 const editAdapter=KIND_TO_ADAPTER[editing?.kind];
 const editingTitle=editing?(editing.kind==='note'?w.note:editing.kind==='photo'?w.photo:(editAdapter?w[ADAPTERS[editAdapter].labelKey]:pinTypeLabel(editing.kind,!String(language).startsWith('en')))):w.title;
 return <FormShell className="card pin-composer pin-composer-v2" onSubmit={onSubmit}>
  <div className="pin-composer-head"><div><small>{editing?w.edit:w.pin}</small><h2>{editingTitle}</h2></div><button type="button" className="icon-btn" onClick={onClose} aria-label={w.cancel}><Icon name="close"/></button></div>

  {!editing&&<FieldGroup legend={w.title} className="pin-composer-root"><div className="pin-composer-root-grid" role="group" aria-label={w.title}>
   {[['note',w.note,'light'],['photo',w.photo,'camera'],['existing',w.existing,'lists']].map(([value,label,icon])=><button type="button" key={value} className={mode===value?'active':''} aria-pressed={mode===value} onClick={()=>chooseMode(value)}><Icon name={icon}/><span>{label}</span></button>)}
  </div></FieldGroup>}

  {(editing?.kind==='note'||(!editing&&mode==='note'))&&<FormField label={w.message}><textarea autoFocus rows={5} maxLength={10000} value={text} onChange={event=>setText(event.target.value)}/></FormField>}

  {!editing&&mode==='photo'&&<><FormField label={w.caption}><textarea rows={3} maxLength={10000} value={text} onChange={event=>setText(event.target.value)}/></FormField><FileDropZone multiple accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif" disabled={busy||files.length>=4} icon="upload" title={w.photos} hint={w.limit} onFiles={addFiles}/><ul className="board-files">{files.map((file,index)=><li key={`${file.name}-${index}`}><FilePreview file={file}/><span>{file.name}</span><button type="button" aria-label={`${w.removePhoto}: ${file.name}`} onClick={()=>setFiles(old=>old.filter((_,position)=>position!==index))}>×</button></li>)}</ul></>}

  {editing?.images?.length>0&&<div className="board-edit-photos">{editing.images.map(image=><div key={image.id}><img src={image.url} alt=""/><button type="button" className="secondary compact" disabled={busy} onClick={()=>removePhoto(image)}>{w.removePhoto}</button></div>)}</div>}

  {!editing&&mode==='existing'&&<div className="pin-existing-picker">
   {preferences.enabled&&preferences.types.length>0&&<FieldGroup legend={w.recent}><div className="pin-recent-types">{preferences.types.map(key=><button type="button" key={key} disabled={busy} onClick={()=>chooseRecentType(key)}><Icon name={ADAPTERS[key].icon}/><span>{w[ADAPTERS[key].labelKey]}</span></button>)}</div></FieldGroup>}
   <FieldGroup legend={w.groups}><div className="pin-source-groups" role="group" aria-label={w.groups}>{GROUPS.map(row=><button type="button" key={row.key} className={group===row.key?'active':''} aria-pressed={group===row.key} onClick={()=>chooseGroup(row.key)}>{w[row.key]}</button>)}</div></FieldGroup>
   {currentGroup.adapters.length>1&&<div className="pin-source-types" role="group" aria-label={w[currentGroup.key]}>{currentGroup.adapters.map(key=><button type="button" key={key} className={activeAdapter===key?'active':''} aria-pressed={activeAdapter===key} onClick={()=>chooseAdapter(key)}><Icon name={ADAPTERS[key].icon}/><span>{w[ADAPTERS[key].labelKey]}</span></button>)}</div>}
   <EntityPicker id="pin-existing-search" label={w.choose} description={w.pickerHint} items={items} selectedIds={targetId?[targetId]:[]} onChange={changeSelection} getItemLabel={itemLabel} multiple={false} placeholder={w.search} emptyMessage={w.empty} loading={pickerBusy} loadingMessage={w.loading} query={query} onQueryChange={changeQuery} filterLocally={false} clearQueryOnChoose={false} selectionLabel={w.selected} removeLabel={w.remove} getRemoveLabel={item=>`${w.remove}: ${item.title||item.id}`} disabled={busy}/>
   {selected&&<div className="pin-choice-preview" aria-live="polite"><span><Icon name={ADAPTERS[activeAdapter]?.icon||pinIconName(kind)}/></span><div><small>{w.selected}</small><strong>{selected.title}</strong>{selected.subtitle&&<span>{String(selected.subtitle)}</span>}</div></div>}
   {pickerBusy&&items.length>0&&<p role="status" className="pin-choice-loading">{w.loading}</p>}
   {pickerError&&<div role="alert" className="pin-picker-error"><span>{pickerError}</span><button type="button" className="secondary" onClick={retryPicker}>{w.retry}</button></div>}
   {hasNext&&!pickerError&&<button type="button" className="secondary pin-picker-more" disabled={pickerBusy||busy} onClick={loadMore}>{pickerBusy?w.loading:w.loadMore}</button>}
   {hintsAuthorized&&scopeKey&&<details className="pin-type-preference"><summary>{w.suggestionSettings}</summary><label><input type="checkbox" checked={preferences.enabled} onChange={event=>changeTypeSuggestions(event.target.checked)} disabled={busy}/><span>{w.showRecent}</span></label><p>{w.recentHint}</p></details>}
  </div>}

  {(!isReference||editing)&&<VisibilityControl w={w} members={members} visibility={visibility} setVisibility={setVisibility} selectedMembershipIds={selectedMembershipIds} setSelectedMembershipIds={setSelectedMembershipIds}/>} 
  {isReference&&!editing&&<p className="pin-privacy"><Icon name="lock"/>{w.inheritVisibility}</p>}{isReference&&<p className="pin-privacy"><Icon name="lock"/>{w.shared}</p>}
  <FormActions><button type="button" className="secondary" onClick={onClose} disabled={busy}>{w.cancel}</button><button className="primary" disabled={busy||!valid}>{busy?w.loading:editing?w.save:w.publish}</button></FormActions>
 </FormShell>;
}

function VisibilityControl({w,members,visibility,setVisibility,selectedMembershipIds,setSelectedMembershipIds}){
 const options=[['private',w.onlyMe,'lock'],['selected',w.selectedPeople,'users'],['family',w.wholeFamily,'home']];
 const toggle=id=>setSelectedMembershipIds(current=>current.includes(String(id))?current.filter(value=>value!==String(id)):[...current,String(id)]);
 return <fieldset><legend>{w.visibleFor}</legend><div className="pin-type-grid" role="group" aria-label={w.visibleFor}>{options.map(([value,label,icon])=><button type="button" key={value} className={visibility===value?'active':''} aria-pressed={visibility===value} onClick={()=>setVisibility(value)}><span><Icon name={icon}/></span>{label}</button>)}</div><small>{visibility==='private'?w.visibilityPrivate:visibility==='selected'?w.visibilitySelected:w.visibilityFamily}</small>{visibility==='selected'&&<div className="pin-event-options" role="group" aria-label={w.choosePeople}>{members.map(member=>{const id=String(member.id),active=selectedMembershipIds.includes(id),name=member.display_name||member.username;return <button type="button" key={id} className={active?'active':''} aria-pressed={active} onClick={()=>toggle(id)}><span className="pin-choice-icon"><Icon name="user"/></span><span className="grow"><strong>{name}</strong></span><span className="pin-choice-check"><Icon name={active?'check':'plus'}/></span></button>})}</div>}</fieldset>;
}

function FilePreview({file}){
 const [url,setUrl]=useState('');
 useEffect(()=>{const value=URL.createObjectURL(file);setUrl(value);return()=>URL.revokeObjectURL(value)},[file]);
 return url?<img className="board-file-preview" src={url} alt=""/>:null;
}
