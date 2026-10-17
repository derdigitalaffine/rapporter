import {useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import {parseShoppingItemInput} from './shopping-item-autoguess.js';
import './shopping-text-i18n';
import './shopping-text-mode.css';

const MAX_IMPORT_LINES=80;
const lines=value=>String(value||'').split(/\r?\n/).map(line=>line.trim()).filter(Boolean);
const cleanListPrefix=value=>String(value||'').replace(/^\s*(?:(?:[-*•])\s+|\d+[.)]\s+|\[[ xX]\]\s+)/,'').trim();

export default function ShoppingTextMode({items=[],onAddMany,onRename,onRemove}){
  const {t}=useTranslation();
  const [draft,setDraft]=useState('');
  const [busy,setBusy]=useState(false);
  const [lineErrors,setLineErrors]=useState({});
  const submitting=useRef(false);
  const rawLines=lines(draft);
  const overLimit=rawLines.length>MAX_IMPORT_LINES;
  const preview=rawLines.slice(0,MAX_IMPORT_LINES).map((raw,index)=>{
    const cleaned=cleanListPrefix(raw);
    return {id:`draft-${index}`,raw,cleaned,parsed:parseShoppingItemInput(cleaned)};
  });

  async function addText(){
    if(!preview.length||overLimit||submitting.current)return;
    submitting.current=true;setBusy(true);setLineErrors({});
    const failed=[];const errors={};
    try{
      // One canonical add at a time: bounded load and exact per-line recovery.
      // queueShoppingAdd itself supplies the stable replay id for each accepted line.
      for(const row of preview){
        try{await onAddMany([row.cleaned])}
        catch(error){failed.push(row.raw);errors[row.id]=error?.message||t('shoppingText.lineFailed')}
      }
      setDraft(failed.join('\n'));
      setLineErrors(errors);
    }finally{
      submitting.current=false;setBusy(false);
    }
  }

  return <section className="shopping-text-mode" aria-labelledby="shopping-text-title">
    <div className="shopping-text-head"><span className="round-icon"><Icon name="edit"/></span><div><strong id="shopping-text-title">{t('shoppingText.title')}</strong><small>{t('shoppingText.hint')}</small></div></div>
    <div className="shopping-text-composer">
      <label htmlFor="shopping-text-input">{t('shoppingText.bulkLabel')}</label>
      <textarea id="shopping-text-input" value={draft} onChange={event=>{setDraft(event.target.value);setLineErrors({})}} placeholder={t('shoppingText.bulkPlaceholder')} disabled={busy}/>
      {preview.length>0&&<div className="shopping-text-preview" aria-label={t('shoppingText.previewTitle')}>
        <div className="shopping-text-preview-head"><strong>{t('shoppingText.previewTitle')}</strong><small>{t('shoppingText.previewCount',{count:preview.length})}</small></div>
        {preview.map(row=>{
          const meta=[row.parsed.values.quantity,row.parsed.values.category].filter(Boolean).join(' · ');
          return <div className="shopping-text-preview-row" key={row.id}><span><strong>{row.parsed.values.name||row.cleaned}</strong><small>{meta||t('shoppingText.noMetadata')}</small></span>{lineErrors[row.id]&&<em role="alert">{lineErrors[row.id]}</em>}</div>;
        })}
      </div>}
      {overLimit&&<p className="shopping-text-limit" role="alert">{t('shoppingText.tooManyLines',{count:MAX_IMPORT_LINES})}</p>}
      <div className="shopping-text-composer-actions"><small>{t('shoppingText.pasteHint')}</small><button className="primary compact" type="button" onClick={addText} disabled={busy||!preview.length||overLimit}><Icon name="plus"/>{busy?t('shoppingText.applying'):t('shoppingText.addLines')}</button></div>
    </div>
    <div className="shopping-text-lines">{items.length?items.map(item=><ShoppingTextLine key={item.id} item={item} onRename={onRename} onRemove={onRemove} t={t}/>):<div className="shopping-text-empty"><Icon name="shopping"/><span>{t('shoppingText.empty')}</span></div>}</div>
  </section>;
}

function ShoppingTextLine({item,onRename,onRemove,t}){
  const [value,setValue]=useState(item.name||'');
  const [saving,setSaving]=useState(false);

  async function save(){
    const next=value.trim();
    if(!next){setValue(item.name||'');return}
    if(next===item.name)return;
    setSaving(true);
    try{await onRename(item,next)}catch{setValue(next);throw new Error('save_failed')}finally{setSaving(false)}
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
