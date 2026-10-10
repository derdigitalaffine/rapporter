import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import {queueShoppingTemplateApply} from './shopping-offline';
import './shopping-template-i18n';
import './shopping-templates.css';

const unwrap=value=>value?.results||value||[];
const cacheKey=(kind,familyId)=>`familyos-shopping-${kind}:${familyId}`;
function readCache(kind,familyId){try{return JSON.parse(localStorage.getItem(cacheKey(kind,familyId))||'[]')}catch{return[]}}
function writeCache(kind,familyId,value){try{localStorage.setItem(cacheKey(kind,familyId),JSON.stringify(value))}catch{}}

export default function ShoppingTemplateTools({familyId,list,onChanged}){
 const {t}=useTranslation();
 const [templates,setTemplates]=useState([]);const [stores,setStores]=useState([]);const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [preview,setPreview]=useState(null);const [templateName,setTemplateName]=useState(list?.name||'');const [manualOpen,setManualOpen]=useState(false);const [manualName,setManualName]=useState('');const [manualItems,setManualItems]=useState('');const [manualStore,setManualStore]=useState('');const [storeOpen,setStoreOpen]=useState(false);const [storeForm,setStoreForm]=useState({name:'',branch_label:'',website_url:'',offers_url:''});const [selectedStore,setSelectedStore]=useState('');const [online,setOnline]=useState(()=>typeof navigator==='undefined'||navigator.onLine);
 const activeStores=stores.filter(store=>store.active!==false);
 const assignedStore=useMemo(()=>stores.find(store=>(store.shopping_list_ids||[]).some(id=>String(id)===String(list?.id)))||null,[stores,list?.id]);

 async function load(){
  if(!familyId)return;
  setError('');
  if(!online){setTemplates(readCache('templates',familyId));setStores(readCache('stores',familyId));return}
  try{
   const [templateRows,storeRows]=await Promise.all([
    api(`/shopping-templates/?family=${encodeURIComponent(familyId)}`),
    api(`/shopping-stores/?family=${encodeURIComponent(familyId)}`),
   ]);
   const nextTemplates=unwrap(templateRows).filter(row=>!row.archived);const nextStores=unwrap(storeRows);
   setTemplates(nextTemplates);setStores(nextStores);writeCache('templates',familyId,nextTemplates);writeCache('stores',familyId,nextStores);
  }catch(e){setTemplates(readCache('templates',familyId));setStores(readCache('stores',familyId));setError(e.message||t('shoppingTemplateUi.loadFailed'))}
 }
 useEffect(()=>{const update=()=>setOnline(navigator.onLine);window.addEventListener('online',update);window.addEventListener('offline',update);return()=>{window.removeEventListener('online',update);window.removeEventListener('offline',update)}},[]);
 useEffect(()=>{setTemplateName(list?.name||'');setPreview(null);void load()},[familyId,list?.id,online]);
 useEffect(()=>{setSelectedStore(assignedStore?.id||'')},[assignedStore?.id]);

 async function saveCurrent(){
  if(!online||busy||!list)return;
  const itemIds=(list.items||[]).filter(item=>!item._offlinePending).map(item=>item.id);
  if(!itemIds.length){toast(t('shoppingTemplateUi.invalidItems'),{type:'error'});return}
  setBusy(true);setError('');
  try{
   const saved=await api('/shopping-templates/from-list/',{method:'POST',body:JSON.stringify({shopping_list:list.id,name:(templateName||list.name).trim(),item_ids:itemIds,default_store:assignedStore?.id||null})});
   setTemplates(rows=>[...rows,saved].sort((a,b)=>a.name.localeCompare(b.name)));setTemplateName(list.name||'');toast(t('shoppingTemplateUi.created'),{type:'success'});await load();
  }catch(e){setError(e.message);toast(e.message||t('shoppingTemplateUi.loadFailed'),{type:'error'})}finally{setBusy(false)}
 }
 async function createManual(e){
  e.preventDefault();if(!online||busy)return;
  const names=[...new Set(manualItems.split(/\r?\n/).map(value=>value.trim()).filter(Boolean))];
  if(!manualName.trim()||!names.length){toast(t('shoppingTemplateUi.invalidItems'),{type:'error'});return}
  setBusy(true);setError('');
  try{
   await api('/shopping-templates/',{method:'POST',body:JSON.stringify({family:familyId,name:manualName.trim(),default_store:manualStore||null,items:names.map((name,position)=>({name,position}))})});
   setManualName('');setManualItems('');setManualStore('');setManualOpen(false);toast(t('shoppingTemplateUi.created'),{type:'success'});await load();
  }catch(e){setError(e.message);toast(e.message||t('shoppingTemplateUi.loadFailed'),{type:'error'})}finally{setBusy(false)}
 }
 async function inspect(template){
  if(!online||!list)return;
  setBusy(true);setError('');
  try{const result=await api(`/shopping-templates/${template.id}/preview/?shopping_list=${encodeURIComponent(list.id)}`);setPreview({template,result})}catch(e){setError(e.message)}finally{setBusy(false)}
 }
 async function applyTemplate(template){
  if(busy||!list)return;
  if(!online){
   await queueShoppingTemplateApply(familyId,template.id,list.id);toast(t('shoppingTemplateUi.applyQueued'),{type:'success'});return;
  }
  setBusy(true);setError('');
  try{
   const result=await api(`/shopping-templates/${template.id}/apply/`,{method:'POST',body:JSON.stringify({shopping_list:list.id})});
   toast(t('shoppingTemplateUi.applyDone',{created:result.created,reopened:result.reopened,already:result.already_open}),{type:'success'});setPreview(null);await onChanged?.();
  }catch(e){setError(e.message);toast(e.message||t('shoppingTemplateUi.loadFailed'),{type:'error'})}finally{setBusy(false)}
 }
 async function createList(template){
  if(!online||busy)return;
  setBusy(true);setError('');
  try{
   const created=await api(`/shopping-templates/${template.id}/create-list/`,{method:'POST',body:JSON.stringify({})});
   toast(t('shoppingTemplateUi.listCreated'),{type:'success'});window.location.assign(`/?page=shopping&list=${encodeURIComponent(created.id)}`);
  }catch(e){setError(e.message);toast(e.message||t('shoppingTemplateUi.loadFailed'),{type:'error'})}finally{setBusy(false)}
 }
 async function createStore(e){
  e.preventDefault();if(!online||busy||!storeForm.name.trim())return;
  setBusy(true);setError('');
  try{
   const saved=await api('/shopping-stores/',{method:'POST',body:JSON.stringify({family:familyId,name:storeForm.name.trim(),branch_label:storeForm.branch_label.trim(),website_url:storeForm.website_url.trim(),offers_url:storeForm.offers_url.trim()})});
   setStoreForm({name:'',branch_label:'',website_url:'',offers_url:''});setStoreOpen(false);setSelectedStore(saved.id);toast(t('shoppingTemplateUi.storeSaved'),{type:'success'});await load();
  }catch(e){setError(e.message);toast(e.message||t('shoppingTemplateUi.loadFailed'),{type:'error'})}finally{setBusy(false)}
 }
 async function changeStoreAssignment(){
  if(!online||busy||!list)return;
  if(String(selectedStore||'')===String(assignedStore?.id||''))return;
  setBusy(true);setError('');
  try{
   if(selectedStore){await api(`/shopping-stores/${selectedStore}/assign/`,{method:'POST',body:JSON.stringify({shopping_list:list.id})});toast(t('shoppingTemplateUi.assigned'),{type:'success'})}
   else if(assignedStore){
    await api(`/shopping-stores/${assignedStore.id}/unassign/`,{method:'POST',body:JSON.stringify({shopping_list:list.id})});
    if(list.store===assignedStore.display_label)await api(`/shopping-lists/${list.id}/`,{method:'PATCH',body:JSON.stringify({store:''})});
    toast(t('shoppingTemplateUi.assignmentRemoved'),{type:'success'});
   }
   await load();await onChanged?.();
  }catch(e){setError(e.message);toast(e.message||t('shoppingTemplateUi.loadFailed'),{type:'error'})}finally{setBusy(false)}
 }

 return <section className="shopping-template-tools" data-testid="shopping-template-tools"><header><span><Icon name="shopping"/></span><div><h3>{t('shoppingTemplateUi.title')}</h3><p>{t('shoppingTemplateUi.hint')}</p></div></header>{!online&&<div className="template-notice"><Icon name="offline"/><span>{t('shoppingTemplateUi.offline')}</span></div>}{error&&<div className="template-notice error" role="alert"><Icon name="warning"/><span>{error}</span></div>}
  <div className="template-section"><div className="template-section-head"><div><h4>{t('shoppingTemplateUi.templates')}</h4><p className="template-hint">{t('shoppingTemplateUi.manageHint')}</p></div><button type="button" className="secondary compact" onClick={()=>setManualOpen(value=>!value)} disabled={!online||busy}><Icon name="plus"/>{t('shoppingTemplateUi.newTemplate')}</button></div>
   {manualOpen&&<form className="template-inline-form" onSubmit={createManual}><label>{t('shoppingTemplateUi.templateName')}<input value={manualName} onChange={e=>setManualName(e.target.value)} required/></label><label>{t('shoppingTemplateUi.itemsOnePerLine')}<textarea value={manualItems} onChange={e=>setManualItems(e.target.value)} required/></label><label>{t('shoppingTemplateUi.defaultStore')}<select value={manualStore} onChange={e=>setManualStore(e.target.value)}><option value="">{t('shoppingTemplateUi.noStore')}</option>{activeStores.map(store=><option key={store.id} value={store.id}>{store.display_label}</option>)}</select></label><div className="template-actions"><button className="primary compact" disabled={busy}><Icon name="check"/>{t('shoppingTemplateUi.saveTemplate')}</button><button type="button" className="secondary compact" onClick={()=>setManualOpen(false)}>{t('cancel')}</button></div></form>}
   {list&&<div className="template-inline-form"><label>{t('shoppingTemplateUi.saveCurrent')}<input value={templateName} onChange={e=>setTemplateName(e.target.value)} placeholder={t('shoppingTemplateUi.templateName')}/></label><button type="button" className="secondary compact" onClick={saveCurrent} disabled={!online||busy||!(list.items||[]).length}><Icon name="archive"/>{t('shoppingTemplateUi.saveTemplate')}</button></div>}
   <div className="template-grid">{templates.length?templates.map(template=><article className="template-card" key={template.id}><div className="template-card-main"><span><Icon name="lists"/></span><div><strong>{template.name}</strong><small>{template.item_count} · {template.default_store_label||t('shoppingTemplateUi.noStore')}</small></div></div>{preview?.template.id===template.id&&<div className="template-preview">{t('shoppingTemplateUi.previewText',{created:preview.result.created,reopened:preview.result.reopened,already:preview.result.already_open})}</div>}<div className="template-actions"><button type="button" className="secondary compact" onClick={()=>inspect(template)} disabled={!online||busy||!list}><Icon name="info"/>{t('shoppingTemplateUi.preview')}</button><button type="button" className="primary compact" onClick={()=>applyTemplate(template)} disabled={busy||!list}><Icon name="check"/>{t('shoppingTemplateUi.apply')}</button><button type="button" className="secondary compact" onClick={()=>createList(template)} disabled={!online||busy}><Icon name="plus"/>{t('shoppingTemplateUi.createList')}</button></div></article>):<div className="template-notice"><Icon name="lists"/><span>{t('shoppingTemplateUi.empty')}</span></div>}</div>
  </div>
  <div className="template-section"><div className="template-section-head"><h4>{t('shoppingTemplateUi.stores')}</h4><button type="button" className="secondary compact" onClick={()=>setStoreOpen(value=>!value)} disabled={!online||busy}><Icon name="plus"/>{t('shoppingTemplateUi.addStore')}</button></div>{assignedStore&&<div className="template-store-summary"><Icon name="store"/><div><strong>{assignedStore.display_label}</strong><small>{assignedStore.address||assignedStore.website_url||t('shoppingTemplateUi.assigned')}</small></div>{assignedStore.offers_url&&<a className="secondary compact" href={assignedStore.offers_url} target="_blank" rel="noopener noreferrer">{t('shoppingTemplateUi.offersOpen')} <Icon name="next"/></a>}</div>}
   {storeOpen&&<form className="template-inline-form" onSubmit={createStore}><label>{t('shoppingTemplateUi.storeName')}<input value={storeForm.name} onChange={e=>setStoreForm(value=>({...value,name:e.target.value}))} required/></label><label>{t('shoppingTemplateUi.branch')}<input value={storeForm.branch_label} onChange={e=>setStoreForm(value=>({...value,branch_label:e.target.value}))}/></label><label>{t('shoppingTemplateUi.website')}<input type="url" inputMode="url" value={storeForm.website_url} onChange={e=>setStoreForm(value=>({...value,website_url:e.target.value}))} placeholder="https://"/></label><label>{t('shoppingTemplateUi.offers')}<input type="url" inputMode="url" value={storeForm.offers_url} onChange={e=>setStoreForm(value=>({...value,offers_url:e.target.value}))} placeholder="https://"/></label><div className="template-actions"><button className="primary compact" disabled={busy}><Icon name="check"/>{t('shoppingTemplateUi.addStore')}</button><button type="button" className="secondary compact" onClick={()=>setStoreOpen(false)}>{t('cancel')}</button></div></form>}
   {list&&activeStores.length>0&&<div className="template-store-row"><label>{t('shoppingTemplateUi.assignStore')}<select value={selectedStore} onChange={e=>setSelectedStore(e.target.value)}><option value="">{t('shoppingTemplateUi.unassigned')}</option>{activeStores.map(store=><option key={store.id} value={store.id}>{store.display_label}</option>)}</select></label><button type="button" className="secondary compact" onClick={changeStoreAssignment} disabled={!online||busy||String(selectedStore||'')===String(assignedStore?.id||'')}><Icon name="store"/>{selectedStore?t('shoppingTemplateUi.assign'):t('shoppingTemplateUi.removeAssignment')}</button></div>}
  </div>
 </section>
}
