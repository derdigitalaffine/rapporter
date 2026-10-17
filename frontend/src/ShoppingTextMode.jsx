import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import {createShoppingMutationId,stageShoppingAddMutationId} from './shopping-offline';
import {parseShoppingTextDraft,reconcileShoppingTextLineIds,SHOPPING_TEXT_MAX_LINES} from './shopping-text-draft.js';
import './shopping-text-i18n';
import './shopping-text-mode.css';

export default function ShoppingTextMode({items=[],onAddMany,onRename,onRemove}){
  const {t}=useTranslation();
  const [draft,setDraft]=useState('');
  const [busy,setBusy]=useState(false);
  const [lineErrors,setLineErrors]=useState({});
  const submitting=useRef(false);
  const lineMutationIds=useRef(new Map());
  const {rows:preview,overLimit}=parseShoppingTextDraft(draft);

  function changeDraft(nextDraft){
    const nextRows=parseShoppingTextDraft(nextDraft).rows;
    lineMutationIds.current=reconcileShoppingTextLineIds(preview,nextRows,lineMutationIds.current,createShoppingMutationId);
    setDraft(nextDraft);setLineErrors({});
  }

  async function addText(){
    if(!preview.length||overLimit||submitting.current)return;
    submitting.current=true;setBusy(true);setLineErrors({});
    const failed=[];
    try{
      // Keep one stable id per draft line and stage it immediately before the
      // existing canonical single-item write. Processing stays bounded to one.
      for(const row of preview){
        const mutationId=lineMutationIds.current.get(row.signature)||createShoppingMutationId();
        lineMutationIds.current.set(row.signature,mutationId);
        stageShoppingAddMutationId(row.cleaned,mutationId);
        try{await onAddMany([row.cleaned])}
        catch(error){failed.push({raw:row.raw,error:error?.message||t('shoppingText.lineFailed'),mutationId})}
      }
      const failedDraft=failed.map(row=>row.raw).join('\n');
      const failedRows=parseShoppingTextDraft(failedDraft).rows;
      lineMutationIds.current=new Map(failedRows.map((row,index)=>[row.signature,failed[index].mutationId]));
      setDraft(failedDraft);
      setLineErrors(Object.fromEntries(failed.map((row,index)=>[`draft-${index}`,row.error])));
    }finally{
      submitting.current=false;setBusy(false);
    }
  }

  return <section className="shopping-text-mode" aria-labelledby="shopping-text-title">
    <div className="shopping-text-head"><span className="round-icon"><Icon name="edit"/></span><div><strong id="shopping-text-title">{t('shoppingText.title')}</strong><small>{t('shoppingText.hint')}</small></div></div>
    <div className="shopping-text-composer">
      <label htmlFor="shopping-text-input">{t('shoppingText.bulkLabel')}</label>
      <textarea id="shopping-text-input" value={draft} onChange={event=>changeDraft(event.target.value)} placeholder={t('shoppingText.bulkPlaceholder')} disabled={busy}/>
      {preview.length>0&&<div className="shopping-text-preview" aria-label={t('shoppingText.previewTitle')}>
        <div className="shopping-text-preview-head"><strong>{t('shoppingText.previewTitle')}</strong><small>{t('shoppingText.previewCount',{count:preview.length})}</small></div>
        {preview.map(row=>{
          const meta=[row.parsed.values.quantity,row.parsed.values.category].filter(Boolean).join(' · ');
          return <div className="shopping-text-preview-row" key={row.signature}><span><strong>{row.parsed.values.name||row.cleaned}</strong><small>{meta||t('shoppingText.noMetadata')}</small></span>{lineErrors[row.id]&&<em role="alert">{lineErrors[row.id]}</em>}</div>;
        })}
      </div>}
      {overLimit&&<p className="shopping-text-limit" role="alert">{t('shoppingText.tooManyLines',{count:SHOPPING_TEXT_MAX_LINES})}</p>}
      <div className="shopping-text-composer-actions"><small>{t('shoppingText.pasteHint')}</small><button className="primary compact" type="button" onClick={addText} disabled={busy||!preview.length||overLimit}><Icon name="plus"/>{busy?t('shoppingText.applying'):t('shoppingText.addLines')}</button></div>
    </div>
    <div className="shopping-text-lines">{items.length?items.map(item=><ShoppingTextLine key={item.id} item={item} onRename={onRename} onRemove={onRemove} t={t}/>):<div className="shopping-text-empty"><Icon name="shopping"/><span>{t('shoppingText.empty')}</span></div>}</div>
  </section>;
}

function ShoppingTextLine({item,onRename,onRemove,t}){
  const [value,setValue]=useState(item.name||'');
  const [saving,setSaving]=useState(false);
  useEffect(()=>setValue(item.name||''),[item.id,item.name]);

  async function save(){
    const next=value.trim();
    if(!next){setValue(item.name||'');return}
    if(next===item.name)return;
    setSaving(true);
    try{await onRename(item,next)}finally{setSaving(false)}
  }

  function onKeyDown(event){
    if(event.key==='Enter'){event.preventDefault();event.currentTarget.blur()}
    if(event.key==='Escape'){event.preventDefault();setValue(item.name||'');event.currentTarget.blur()}
  }

  const meta=[item.quantity,item.category,item.aisle].filter(Boolean).join(' · ');
  return <div className="shopping-text-line">
    <div className="shopping-text-line-main"><input value={value} onChange={event=>setValue(event.target.value)} onBlur={()=>void save()} onKeyDown={onKeyDown} aria-label={t('shoppingText.editLabel',{name:item.name})} disabled={saving}/>{meta&&<small>{meta}</small>}</div>
    <button className="shopping-text-remove" type="button" onClick={()=>onRemove(item)} aria-label={t('shoppingText.removeLabel',{name:item.name})}><Icon name="delete"/></button>
  </div>;
}
