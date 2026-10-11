import {useEffect,useMemo,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';

const uid=()=>`item_${Date.now().toString(36)}_${Math.random().toString(36).slice(2,8)}`;

function localDateTime(value){
 if(!value)return'';
 const date=new Date(value);if(Number.isNaN(date.getTime()))return'';
 const offset=date.getTimezoneOffset()*60000;
 return new Date(date.getTime()-offset).toISOString().slice(0,16);
}
function toIso(value){if(!value)return null;const date=new Date(value);return Number.isNaN(date.getTime())?null:date.toISOString()}

export default function NoteExtendedEditor({family,blocks=[],readonly,status,onChange,onConvert,converting,t}){
 const [documents,setDocuments]=useState([]),[documentChoice,setDocumentChoice]=useState('');
 useEffect(()=>{
  let active=true;setDocuments([]);setDocumentChoice('');
  if(!family?.id)return()=>{active=false};
  api(`/documents/?family=${encodeURIComponent(family.id)}`).then(data=>{if(active)setDocuments(data?.results||data||[])}).catch(()=>{if(active)setDocuments([])});
  return()=>{active=false};
 },[family?.id]);
 const documentsById=useMemo(()=>new Map(documents.map(row=>[String(row.id),row])),[documents]);
 const update=(index,patch)=>onChange(blocks.map((block,i)=>i===index?{...block,...patch}:block));
 const remove=index=>onChange(blocks.filter((_,i)=>i!==index));
 const add=type=>{
  const block=type==='paragraph'?{type,text:''}:type==='heading'?{type,text:t('newHeading'),level:2}:type==='panel'?{type,tone:'info',text:''}:{type:'checklist',items:[]};
  onChange([...blocks,block]);
 };
 const addDocument=()=>{if(!documentChoice)return;onChange([...blocks,{type:'document',document_id:documentChoice}]);setDocumentChoice('')};
 const updateItem=(blockIndex,itemIndex,patch)=>{
  const block=blocks[blockIndex];
  const items=block.items.map((item,index)=>index===itemIndex?{...item,...patch}:item);
  update(blockIndex,{items});
 };
 const addItem=blockIndex=>{
  const block=blocks[blockIndex];
  update(blockIndex,{items:[...block.items,{id:uid(),text:t('newChecklistItem'),checked:false}]});
 };
 const removeItem=(blockIndex,itemIndex)=>{
  const block=blocks[blockIndex];
  update(blockIndex,{items:block.items.filter((_,index)=>index!==itemIndex)});
 };
 return <section className="note-extended" aria-label={t('blocks')}>
  <div className="note-extended-head"><div><h2>{t('blocks')}</h2><p>{t('extendedHint')}</p></div>{!readonly&&<div className="note-block-add" role="group" aria-label={t('addBlock')}>
   <button type="button" className="secondary compact" onClick={()=>add('paragraph')}><Icon name="edit"/>{t('addParagraph')}</button>
   <button type="button" className="secondary compact" onClick={()=>add('heading')}>{t('addHeading')}</button>
   <button type="button" className="secondary compact" onClick={()=>add('panel')}>{t('addPanel')}</button>
   <button type="button" className="secondary compact" onClick={()=>add('checklist')}><Icon name="tasks"/>{t('addChecklist')}</button>
  </div>}</div>
  {!readonly&&<div className="note-block-grid note-document-picker"><label className="grow"><span>{t('documentChoice')}</span><select value={documentChoice} onChange={e=>setDocumentChoice(e.target.value)}><option value="">{t('chooseDocument')}</option>{documents.map(document=><option key={document.id} value={document.id}>{document.title}</option>)}</select></label><button type="button" className="secondary compact" disabled={!documentChoice} onClick={addDocument}>{t('addDocument')}</button></div>}
  {!blocks.length&&<p className="note-extended-empty">{t('blocksEmpty')}</p>}
  <div className="note-block-list">{blocks.map((block,index)=>{const document=block.type==='document'?documentsById.get(String(block.document_id)):null;return <article className="note-block" key={`${block.type}-${index}`}>
   <div className="note-block-head"><strong>{t(`block_${block.type}`)}</strong>{!readonly&&<button type="button" className="ghost-danger compact" onClick={()=>remove(index)} aria-label={`${t('removeBlock')} ${index+1}`}>{t('remove')}</button>}</div>
   {block.type==='paragraph'&&<label><span>{t('paragraphText')}</span><textarea rows={5} maxLength={10000} readOnly={readonly} value={block.text||''} onChange={e=>update(index,{text:e.target.value})}/></label>}
   {block.type==='heading'&&<div className="note-block-grid"><label><span>{t('headingLevel')}</span><select disabled={readonly} value={block.level||2} onChange={e=>update(index,{level:Number(e.target.value)})}><option value="2">H2</option><option value="3">H3</option></select></label><label className="grow"><span>{t('headingText')}</span><input maxLength={500} readOnly={readonly} value={block.text||''} onChange={e=>update(index,{text:e.target.value})}/></label></div>}
   {block.type==='panel'&&<><label><span>{t('panelTone')}</span><select disabled={readonly} value={block.tone||'info'} onChange={e=>update(index,{tone:e.target.value})}><option value="info">{t('info')}</option><option value="warning">{t('warning')}</option></select></label><label><span>{t('panelText')}</span><textarea rows={4} maxLength={5000} readOnly={readonly} value={block.text||''} onChange={e=>update(index,{text:e.target.value})}/></label></>}
   {block.type==='document'&&<div className="note-block-grid note-document-ref">{document?<><a href={document.file_url||`/api/documents/${encodeURIComponent(block.document_id)}/file/`} target="_blank" rel="noreferrer">{document.title}</a><small>{document.mime_type||t('document')}</small></>:<span className="note-extended-empty">{t('documentUnavailable')}</span>}</div>}
   {block.type==='checklist'&&<div className="note-checklist"><div className="note-checklist-head"><span>{t('checklistHint')}</span>{!readonly&&<button type="button" className="secondary compact" onClick={()=>addItem(index)}><Icon name="plus"/>{t('addChecklistItem')}</button>}</div>{!block.items?.length&&<p className="note-extended-empty">{t('checklistEmpty')}</p>}{(block.items||[]).map((item,itemIndex)=><div className="note-checklist-item" key={item.id}>
    <label className="note-check"><input type="checkbox" checked={Boolean(item.checked)} disabled={readonly} onChange={e=>updateItem(index,itemIndex,{checked:e.target.checked})}/><span className="sr-only">{t('checked')}</span></label>
    <label className="note-check-text"><span>{t('itemText')}</span><input maxLength={180} readOnly={readonly} value={item.text||''} onChange={e=>updateItem(index,itemIndex,{text:e.target.value})}/></label>
    <label><span>{t('due')}</span><input type="datetime-local" readOnly={readonly} value={localDateTime(item.due_at)} onChange={e=>updateItem(index,itemIndex,{due_at:toIso(e.target.value)})}/></label>
    <label><span>{t('assignee')}</span><select disabled={readonly} value={item.assignee||''} onChange={e=>updateItem(index,itemIndex,{assignee:e.target.value?Number(e.target.value):null})}><option value="">{t('nobody')}</option>{(family?.memberships||[]).map(member=><option value={member.user} key={member.id}>{member.display_name||member.username||member.user}</option>)}</select></label>
    <div className="note-check-actions">{item.task_id?<span className="note-task-created"><Icon name="tasks"/>{t('taskCreated')}</span>:!readonly&&<button type="button" className="secondary compact" disabled={status!=='saved'||converting===item.id||!item.text?.trim()} onClick={()=>onConvert(item.id)}>{converting===item.id?t('convertingTask'):t('convertTask')}</button>}{!readonly&&<button type="button" className="ghost-danger compact" onClick={()=>removeItem(index,itemIndex)} aria-label={t('removeItem')}>{t('remove')}</button>}</div>
   </div>)}</div>}
  </article>})}</div>
 </section>
}
