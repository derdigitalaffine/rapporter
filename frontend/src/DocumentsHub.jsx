import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import './documents-i18n';
import './documents.css';

const SHARE_CACHE='familyos-share-target-v1';
const ACCEPTED_TYPES=new Set(['application/pdf','image/jpeg','image/png','image/webp']);
const ACCEPTED_NAME=/\.(?:pdf|jpe?g|png|webp)$/i;
const ACCEPT='application/pdf,image/jpeg,image/png,image/webp';
const KINDS=['generic','letter','contract','receipt','insurance','invoice'];

function stem(name){return String(name||'Dokument').replace(/\.[^.]+$/,'').trim()||'Dokument'}
function isAccepted(file){return ACCEPTED_TYPES.has(file.type)||ACCEPTED_NAME.test(file.name||'')}
function pendingFile(file,title=''){return {id:crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`,file,title:title||stem(file.name),kind:'generic',visibility:'private'}}
function sharePath(batch,suffix){return `/__familyos_share__/${batch}/${suffix}`}

async function consumeShareBatch(batch){
 if(!('caches'in window))throw new Error('cache_unavailable');
 const cache=await caches.open(SHARE_CACHE);
 const metaResponse=await cache.match(sharePath(batch,'meta'));
 if(!metaResponse)throw new Error('share_missing');
 const metadata=await metaResponse.json();
 const files=[];
 for(const row of metadata.files||[]){
  const response=await cache.match(sharePath(batch,`file/${row.index}`));
  if(!response)continue;
  const blob=await response.blob();
  files.push(new File([blob],row.name||`geteilt-${row.index+1}`,{type:row.type||blob.type,lastModified:Date.now()}));
 }
 for(const row of metadata.files||[])await cache.delete(sharePath(batch,`file/${row.index}`));
 await cache.delete(sharePath(batch,'meta'));
 return {metadata,files};
}

export default function DocumentsHub({family,onBack}){
 const {t}=useTranslation();
 const [query,setQuery]=useState('');
 const [kind,setKind]=useState('');
 const [visibility,setVisibility]=useState('');
 const [person,setPerson]=useState('');
 const [correspondent,setCorrespondent]=useState('');
 const [dateFrom,setDateFrom]=useState('');
 const [dateTo,setDateTo]=useState('');
 const [pinned,setPinned]=useState(false);
 const [results,setResults]=useState([]);
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState('');
 const [pending,setPending]=useState([]);
 const [uploading,setUploading]=useState(false);
 const [importMessage,setImportMessage]=useState('');
 const [revision,setRevision]=useState(0);
 const memberships=family?.memberships||[];
 const familyId=family?.id;
 const filters=useMemo(()=>({query,kind,visibility,person,correspondent,dateFrom,dateTo,pinned}),[query,kind,visibility,person,correspondent,dateFrom,dateTo,pinned]);

 useEffect(()=>{
  if(!familyId)return;
  let cancelled=false;
  const timer=setTimeout(async()=>{
   setLoading(true);setError('');
   const params=new URLSearchParams({family:String(familyId)});
   if(filters.query.trim())params.set('q',filters.query.trim());
   if(filters.kind.trim())params.set('kind',filters.kind.trim());
   if(filters.visibility)params.set('visibility',filters.visibility);
   if(filters.person)params.set('person',filters.person);
   if(filters.correspondent.trim())params.set('correspondent',filters.correspondent.trim());
   if(filters.dateFrom)params.set('date_from',filters.dateFrom);
   if(filters.dateTo)params.set('date_to',filters.dateTo);
   if(filters.pinned)params.set('pinned','true');
   try{const response=await api(`/documents/search/?${params}`);if(!cancelled)setResults(response.results||[])}catch(e){if(!cancelled)setError(e.message||'search_failed')}finally{if(!cancelled)setLoading(false)}
  },220);
  return()=>{cancelled=true;clearTimeout(timer)};
 },[familyId,filters,revision]);

 useEffect(()=>{
  const url=new URL(location.href);const batch=url.searchParams.get('share_batch');if(!batch)return;
  let cancelled=false;
  (async()=>{try{const {metadata,files}=await consumeShareBatch(batch);if(cancelled)return;const supported=files.filter(isAccepted);const title=supported.length===1?String(metadata.title||'').trim():'';setPending(rows=>[...rows,...supported.map(file=>pendingFile(file,title))]);setImportMessage(t('documentsUi.sharedFiles',{count:supported.length}))}catch{if(!cancelled)setImportMessage(t('documentsUi.shareUnavailable'))}finally{url.searchParams.delete('share_batch');history.replaceState(history.state,'',`${url.pathname}${url.search}${url.hash}`)}})();
  return()=>{cancelled=true};
 },[familyId,t]);

 function addFiles(fileList){
  const files=Array.from(fileList||[]);let firstError='';const supported=[];
  for(const file of files){if(!isAccepted(file)){firstError=firstError||t('documentsUi.unsupported',{name:file.name});continue}supported.push(pendingFile(file))}
  if(firstError)setImportMessage(firstError);if(supported.length)setPending(rows=>[...rows,...supported]);
 }
 function updatePending(id,field,value){setPending(rows=>rows.map(row=>row.id===id?{...row,[field]:value}:row))}
 async function uploadAll(){
  if(!pending.length||uploading)return;const batch=[...pending];let completed=0;setUploading(true);setImportMessage('');
  try{
   for(let index=0;index<batch.length;index+=1){
    const row=batch[index];const form=new FormData();form.append('family',String(familyId));form.append('title',row.title.trim()||stem(row.file.name));form.append('kind',row.kind||'generic');form.append('visibility',row.visibility||'private');form.append('file',row.file,row.file.name);
    try{await api('/documents/',{method:'POST',body:form});completed+=1}catch(e){setPending(batch.slice(index));if(completed)setRevision(value=>value+1);setImportMessage(e.message||'upload_failed');return}
   }
   setPending([]);setImportMessage(t('documentsUi.uploaded'));setRevision(value=>value+1);
  }finally{setUploading(false)}
 }

 return <div className="documents-hub">
  <div className="documents-head"><button className="icon-button" onClick={onBack} aria-label={t('back')}><Icon name="back"/></button><div><h1>{t('documentsUi.title')}</h1><p>{t('documentsUi.subtitle')}</p></div></div>
  <section className="card documents-import" aria-labelledby="document-import-title">
   <div className="documents-section-head"><div><h2 id="document-import-title">{t('documentsUi.importTitle')}</h2><p>{t('documentsUi.importHint')}</p></div><Icon name="upload" size={24}/></div>
   <label className="documents-file-button"><Icon name="upload"/><span>{t('documentsUi.chooseFiles')}</span><input type="file" accept={ACCEPT} multiple onChange={event=>{addFiles(event.target.files);event.target.value=''}}/></label>
   {importMessage&&<p className="documents-message" role="status">{importMessage}</p>}
   {pending.length>0&&<div className="documents-pending">
    {pending.map(row=><article className="documents-pending-row" key={row.id}>
     <div className="documents-file-meta"><Icon name="receipt"/><div><strong>{row.file.name}</strong><small>{Math.max(1,Math.round(row.file.size/1024))} KB · {t('documentsUi.pending')}</small></div></div>
     <label>{t('documentsUi.documentTitle')}<input autoComplete="off" value={row.title} onChange={e=>updatePending(row.id,'title',e.target.value)}/></label>
     <label>{t('documentsUi.kind')}<select value={row.kind} onChange={e=>updatePending(row.id,'kind',e.target.value)}>{KINDS.map(value=><option value={value} key={value}>{t(`documentsUi.${value}`)}</option>)}</select></label>
     <label>{t('documentsUi.visibilityLabel')}<select value={row.visibility} onChange={e=>updatePending(row.id,'visibility',e.target.value)}><option value="private">{t('documentsUi.private')}</option><option value="family">{t('documentsUi.family')}</option></select></label>
     <button type="button" className="secondary compact" onClick={()=>setPending(rows=>rows.filter(item=>item.id!==row.id))}><Icon name="close"/>{t('documentsUi.remove')}</button>
    </article>)}
    <button type="button" className="primary documents-upload-all" disabled={uploading} onClick={uploadAll}><Icon name={uploading?'refresh':'upload'}/>{uploading?t('documentsUi.uploading'):t('documentsUi.uploadAll',{count:pending.length})}</button>
   </div>}
  </section>

  <section className="card documents-search" aria-labelledby="document-search-title">
   <div className="documents-section-head"><div><h2 id="document-search-title">{t('documentsUi.search')}</h2><p>{t('documentsUi.searchHint')}</p></div><Icon name="search" size={24}/></div>
   <label className="documents-query"><span className="sr-only">{t('documentsUi.search')}</span><Icon name="search"/><input autoComplete="off" value={query} onChange={e=>setQuery(e.target.value)} placeholder={t('documentsUi.searchHint')}/></label>
   <details className="documents-filters"><summary><Icon name="filter"/> {t('documentsUi.filters')}</summary><div className="documents-filter-grid">
    <label>{t('documentsUi.kind')}<input autoComplete="off" list="document-kinds" value={kind} onChange={e=>setKind(e.target.value)}/><datalist id="document-kinds">{KINDS.map(value=><option value={value} key={value}/>)}</datalist></label>
    <label>{t('documentsUi.visibility')}<select value={visibility} onChange={e=>setVisibility(e.target.value)}><option value="">{t('documentsUi.all')}</option><option value="private">{t('documentsUi.private')}</option><option value="family">{t('documentsUi.family')}</option><option value="selected">{t('documentsUi.selected')}</option></select></label>
    <label>{t('documentsUi.person')}<select value={person} onChange={e=>setPerson(e.target.value)}><option value="">{t('documentsUi.all')}</option>{memberships.map(member=><option value={member.id} key={member.id}>{member.display_name||member.username||member.id}</option>)}</select></label>
    <label>{t('documentsUi.correspondent')}<input autoComplete="off" value={correspondent} onChange={e=>setCorrespondent(e.target.value)}/></label>
    <label>{t('documentsUi.dateFrom')}<input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)}/></label>
    <label>{t('documentsUi.dateTo')}<input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)}/></label>
    <label className="documents-check"><input type="checkbox" checked={pinned} onChange={e=>setPinned(e.target.checked)}/><span>{t('documentsUi.pinned')}</span></label>
   </div></details>
  </section>

  <div className="documents-results-head"><strong>{t('documentsUi.results',{count:results.length})}</strong>{loading&&<span role="status"><Icon name="refresh"/> {t('syncing')}</span>}</div>
  {error&&<div className="integration-notice" role="alert"><Icon name="warning"/><span>{error}</span></div>}
  {!loading&&!error&&!results.length&&<div className="smart-empty"><Icon name="search" size={34}/><strong>{t('documentsUi.empty')}</strong></div>}
  <div className="documents-results">{results.map(document=><article className="card document-result" key={document.id}>
   <div className="document-result-main"><div className="document-result-title"><Icon name={document.pinned?'favorite':'receipt'}/><div><strong>{document.correspondent?`${document.correspondent} · ${document.title}`:document.title}</strong><small>{[document.document_date,document.kind,document.visibility].filter(Boolean).join(' · ')}</small></div></div>{document.snippet&&<p>{document.snippet}</p>}</div>
   <div className="document-result-actions"><span>{t('documentsUi.processing',{status:document.processing_status})}</span><a className="secondary compact" href={document.file_url} target="_blank" rel="noreferrer"><Icon name="share"/>{t('documentsUi.open')}</a></div>
  </article>)}</div>
 </div>;
}
