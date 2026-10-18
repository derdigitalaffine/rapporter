import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import {createShoppingMutationId} from './shopping-offline';
import {parseShoppingTextDraft,reconcileShoppingTextLineIds,SHOPPING_TEXT_MAX_LINES} from './shopping-text-draft.js';
import './shopping-text-i18n';
import './shopping-text-mode.css';

const scopedMutationIds=new Map();
const scopedPreviewEdits=new Map();
function scopeMap(root,key){const scope=key||'local';if(!root.has(scope))root.set(scope,new Map());return root.get(scope)}
function replaceScopeMap(root,key,value){root.set(key||'local',value);return value}

export default function ShoppingTextMode({scopeKey='',draft:controlledDraft,onDraftChange,items=[],onAddMany,onRename,onRemove}){
  const {t}=useTranslation();
  const [localDraft,setLocalDraft]=useState('');
  const [busy,setBusy]=useState(false);
  const [lineErrors,setLineErrors]=useState({});
  const [acceptedCount,setAcceptedCount]=useState(0);
  const [,refreshPreview]=useState(0);
  const submitting=useRef(false);
  const draft=controlledDraft===undefined?localDraft:controlledDraft;
  const writeDraft=onDraftChange||setLocalDraft;
  const lineMutationIds=scopeMap(scopedMutationIds,scopeKey);
  const previewEdits=scopeMap(scopedPreviewEdits,scopeKey);
  const {rows:preview,overLimit}=parseShoppingTextDraft(draft);

  function changeDraft(nextDraft){
    const nextRows=parseShoppingTextDraft(nextDraft).rows;
    replaceScopeMap(scopedMutationIds,scopeKey,reconcileShoppingTextLineIds(preview,nextRows,lineMutationIds,createShoppingMutationId));
    const allowed=new Set(nextRows.map(row=>row.signature));for(const signature of [...previewEdits.keys()])if(!allowed.has(signature))previewEdits.delete(signature);
    writeDraft(nextDraft);setLineErrors({});setAcceptedCount(0);
  }

  function rowValues(row){
    const edit=previewEdits.get(row.signature)||{};
    return {
      name:edit.name??row.parsed.values.name??row.cleaned,
      quantity:edit.quantity??row.parsed.values.quantity??'',
      category:edit.category??row.parsed.values.category??'',
    };
  }

  function editRow(row,field,value){
    previewEdits.set(row.signature,{...(previewEdits.get(row.signature)||{}),[field]:value});
    setLineErrors(current=>{if(!current[row.id])return current;const next={...current};delete next[row.id];return next});
    refreshPreview(value=>value+1);
  }

  async function addText(){
    if(!preview.length||overLimit||submitting.current)return;
    submitting.current=true;setBusy(true);setLineErrors({});setAcceptedCount(0);
    const ids=scopeMap(scopedMutationIds,scopeKey);
    const payloads=preview.map(row=>{
      const mutationId=ids.get(row.signature)||createShoppingMutationId();ids.set(row.signature,mutationId);
      return {...rowValues(row),client_mutation_id:mutationId};
    });
    let results;
    try{
      results=await onAddMany(payloads,{partial:true,quiet:true});
    }catch(error){
      results=preview.map(()=>({ok:false,error}));
    }
    const failed=[];let accepted=0;
    preview.forEach((row,index)=>{
      const result=results?.[index]||{ok:false,error:new Error(t('shoppingText.lineFailed'))};
      if(result.ok){accepted++;return}
      failed.push({raw:row.raw,error:result.error?.message||t('shoppingText.lineFailed'),mutationId:ids.get(row.signature),edit:previewEdits.get(row.signature)||{}});
    });
    const failedDraft=failed.map(row=>row.raw).join('\n');
    const failedRows=parseShoppingTextDraft(failedDraft).rows;
    replaceScopeMap(scopedMutationIds,scopeKey,new Map(failedRows.map((row,index)=>[row.signature,failed[index].mutationId])));
    replaceScopeMap(scopedPreviewEdits,scopeKey,new Map(failedRows.map((row,index)=>[row.signature,failed[index].edit])));
    writeDraft(failedDraft);
    setLineErrors(Object.fromEntries(failed.map((row,index)=>[`draft-${index}`,row.error])));
    setAcceptedCount(accepted);
    submitting.current=false;setBusy(false);
  }

  const errorCount=Object.keys(lineErrors).length;
  return <section className="shopping-text-mode" aria-labelledby="shopping-text-title">
    <div className="shopping-text-head"><span className="round-icon"><Icon name="edit"/></span><div><strong id="shopping-text-title">{t('shoppingText.title')}</strong><small>{t('shoppingText.hint')}</small></div></div>
    <div className="shopping-text-composer">
      <label htmlFor={`shopping-text-input-${scopeKey||'local'}`}>{t('shoppingText.bulkLabel')}</label>
      <textarea id={`shopping-text-input-${scopeKey||'local'}`} value={draft} onChange={event=>changeDraft(event.target.value)} placeholder={t('shoppingText.bulkPlaceholder')} disabled={busy}/>
      {preview.length>0&&<div className="shopping-text-preview" aria-label={t('shoppingText.previewTitle')}>
        <div className="shopping-text-preview-head"><strong>{t('shoppingText.previewTitle')}</strong><small>{t('shoppingText.previewCount',{count:preview.length})}</small></div>
        {preview.map(row=>{const values=rowValues(row);return <div className="shopping-text-preview-row" key={row.signature}>
          <label><span>{t('shoppingText.nameField')}</span><input value={values.name} onChange={event=>editRow(row,'name',event.target.value)} disabled={busy}/></label>
          <label><span>{t('shoppingText.quantityField')}</span><input value={values.quantity} onChange={event=>editRow(row,'quantity',event.target.value)} placeholder={t('shoppingText.optional')} disabled={busy}/></label>
          <label><span>{t('shoppingText.categoryField')}</span><input value={values.category} onChange={event=>editRow(row,'category',event.target.value)} placeholder={t('shoppingText.optional')} disabled={busy}/></label>
          {lineErrors[row.id]&&<em role="alert">{lineErrors[row.id]}</em>}
        </div>})}
      </div>}
      {overLimit&&<p className="shopping-text-limit" role="alert">{t('shoppingText.tooManyLines',{count:SHOPPING_TEXT_MAX_LINES})}</p>}
      {errorCount>1&&<p className="shopping-text-error-summary" role="alert">{t('shoppingText.errorSummary',{count:errorCount})}</p>}
      {acceptedCount>0&&<p className="shopping-text-accepted" role="status">{t('shoppingText.accepted',{count:acceptedCount})}</p>}
      <div className="shopping-text-composer-actions"><small>{t('shoppingText.pasteHint')}</small><button className="primary compact" type="button" onClick={addText} disabled={busy||!preview.length||overLimit}><Icon name="plus"/>{busy?t('shoppingText.applying'):t('shoppingText.addLines')}</button></div>
    </div>
    <div className="shopping-text-lines">{items.length?items.map(item=><ShoppingTextLine key={item.id} item={item} onRename={onRename} onRemove={onRemove} t={t}/>):<div className="shopping-text-empty"><Icon name="shopping"/><span>{t('shoppingText.empty')}</span></div>}</div>
  </section>;
}

function ShoppingTextLine({item,onRename,onRemove,t}){
  const [value,setValue]=useState(item.name||'');
  const [saving,setSaving]=useState(false);
  const [saveError,setSaveError]=useState('');
  useEffect(()=>{setValue(item.name||'');setSaveError('')},[item.id,item.name]);

  async function save(){
    const next=value.trim();
    if(!next){setValue(item.name||'');setSaveError('');return}
    if(next===item.name){setSaveError('');return}
    setSaving(true);setSaveError('');
    try{await onRename(item,next)}catch(error){setSaveError(error?.message||t('shoppingText.lineFailed'))}finally{setSaving(false)}
  }

  function onKeyDown(event){
    if(event.key==='Enter'){event.preventDefault();event.currentTarget.blur()}
    if(event.key==='Escape'){event.preventDefault();setValue(item.name||'');setSaveError('');event.currentTarget.blur()}
  }

  const meta=[item.quantity,item.category,item.aisle].filter(Boolean).join(' · ');
  return <div className="shopping-text-line">
    <div className="shopping-text-line-main"><input value={value} onChange={event=>{setValue(event.target.value);setSaveError('')}} onBlur={()=>void save()} onKeyDown={onKeyDown} aria-label={t('shoppingText.editLabel',{name:item.name})} aria-invalid={saveError?'true':undefined} disabled={saving}/>{meta&&<small>{meta}</small>}{saveError&&<em role="alert">{saveError}</em>}</div>
    <button className="shopping-text-remove" type="button" onClick={()=>onRemove(item)} aria-label={t('shoppingText.removeLabel',{name:item.name})}><Icon name="delete"/></button>
  </div>;
}
