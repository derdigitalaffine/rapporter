import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import {useDirtyForm} from './dirty-state';
import './shopping-text-i18n';
import './shopping-text-mode.css';

export const shoppingTextLines=value=>String(value||'').split(/\r?\n/).map(line=>line.trim()).filter(Boolean);

export default function ShoppingTextMode({items=[],onAddMany,onRename,onRemove}){
  const {t}=useTranslation();
  const [draft,setDraft]=useState('');
  const [busy,setBusy]=useState(false);
  const textareaRef=useRef(null);
  useDirtyForm(Boolean(draft.trim()));

  async function addText(value=draft){
    const names=shoppingTextLines(value);
    if(!names.length||busy)return;
    setBusy(true);
    try{
      await onAddMany(names);
      setDraft('');
      requestAnimationFrame(()=>textareaRef.current?.focus());
    }finally{setBusy(false)}
  }

  function onKeyDown(event){
    if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();void addText()}
  }

  function onPaste(event){
    const text=event.clipboardData.getData('text');
    const names=shoppingTextLines(text);
    if(names.length<2)return;
    event.preventDefault();
    void addText(text);
  }

  return <section className="shopping-text-mode" aria-labelledby="shopping-text-title">
    <div className="shopping-text-head"><span className="round-icon"><Icon name="edit"/></span><div><strong id="shopping-text-title">{t('shoppingText.title')}</strong><small>{t('shoppingText.hint')}</small></div></div>
    <div className="shopping-text-composer">
      <label htmlFor="shopping-text-input">{t('shoppingText.bulkLabel')}</label>
      <textarea id="shopping-text-input" ref={textareaRef} value={draft} onChange={event=>setDraft(event.target.value)} onKeyDown={onKeyDown} onPaste={onPaste} placeholder={t('shoppingText.bulkPlaceholder')} disabled={busy} autoFocus/>
      <div className="shopping-text-composer-actions"><small>{t('shoppingText.pasteHint')}</small><button className="primary compact" type="button" onClick={()=>addText()} disabled={busy||!shoppingTextLines(draft).length}><Icon name="plus"/>{t('shoppingText.addLines')}</button></div>
    </div>
    <div className="shopping-text-lines">{items.length?items.map(item=><ShoppingTextLine key={item.id} item={item} onRename={onRename} onRemove={onRemove} t={t}/>):<div className="shopping-text-empty"><Icon name="shopping"/><span>{t('shoppingText.empty')}</span></div>}</div>
  </section>;
}

function ShoppingTextLine({item,onRename,onRemove,t}){
  const [value,setValue]=useState(item.name||'');
  const [saving,setSaving]=useState(false);
  const dirty=value.trim()!==String(item.name||'').trim();
  useDirtyForm(dirty);
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
    <div className="shopping-text-line-main"><input value={value} onChange={event=>setValue(event.target.value)} onBlur={save} onKeyDown={onKeyDown} aria-label={t('shoppingText.editLabel',{name:item.name})} disabled={saving}/>{meta&&<small>{meta}</small>}</div>
    <button className="shopping-text-remove" type="button" onClick={()=>onRemove(item)} aria-label={t('shoppingText.removeLabel',{name:item.name})} disabled={saving}><Icon name="delete"/></button>
  </div>;
}
