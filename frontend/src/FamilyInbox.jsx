import {useEffect,useMemo,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import {useFamilyPermissions} from './family-permissions';
import './family-inbox.css';

const unwrap=value=>value?.results||value||[];
const writerRoles=new Set(['owner','adult','teen']);

export default function FamilyInbox({family,t,onBack,onChanged}){
  const {role}=useFamilyPermissions(family);
  const [items,setItems]=useState([]);
  const [filter,setFilter]=useState('all');
  const [compose,setCompose]=useState(false);
  const [body,setBody]=useState('');
  const [important,setImportant]=useState(false);
  const [audience,setAudience]=useState('family');
  const [recipientIds,setRecipientIds]=useState([]);
  const [busy,setBusy]=useState(false);
  const canWrite=writerRoles.has(role);
  const members=family?.memberships||[];

  async function load(){
    const rows=unwrap(await api('/inbox/'));
    setItems(rows.filter(row=>String(row.family)===String(family?.id)));
  }

  useEffect(()=>{load().catch(error=>toast(error.message||t('saveFailed'),{type:'error'}))},[family?.id]);

  const visible=useMemo(()=>items.filter(item=>{
    if(item.withdrawn_at&&item.status==='withdrawn')return item.can_withdraw;
    if(filter==='unread')return item.unread;
    if(filter==='family')return item.source==='manual_message';
    if(filter==='system')return item.source!=='manual_message';
    return true;
  }),[items,filter]);

  async function send(event){
    event.preventDefault();
    if(!body.trim())return;
    if(audience==='selected'&&!recipientIds.length){toast('Bitte mindestens eine Person auswählen.',{type:'error'});return}
    setBusy(true);
    try{
      await api('/inbox/',{method:'POST',body:JSON.stringify({family:family.id,body:body.trim(),important,audience,recipient_ids:audience==='selected'?recipientIds:[]})});
      setBody('');setImportant(false);setAudience('family');setRecipientIds([]);setCompose(false);
      await load();await onChanged?.();toast('Mitteilung gesendet.',{type:'success'});
    }catch(error){toast(error.message||t('saveFailed'),{type:'error'})}finally{setBusy(false)}
  }

  async function act(item,kind){
    try{
      await api(`/inbox/${item.id}/${kind}/`,{method:'POST',body:'{}'});
      await load();await onChanged?.();
    }catch(error){toast(error.message||t('saveFailed'),{type:'error'})}
  }

  async function openItem(item){if(item.unread)await act(item,'read')}
  function toggleRecipient(id){setRecipientIds(current=>current.includes(id)?current.filter(value=>value!==id):[...current,id])}

  return <section className="family-inbox-page">
    <div className="page-head"><button className="back-button" onClick={onBack} aria-label="Zurück"><Icon name="back"/></button><div className="grow"><h1>Mitteilungen</h1><p className="family-inbox-subtitle">Familiennachrichten und eingehende Hinweise an einem Ort.</p></div>{canWrite&&<button className="small-action family-message-new" onClick={()=>setCompose(value=>!value)}><Icon name="plus"/> Mitteilung</button>}</div>

    {compose&&<form className="card family-message-compose" onSubmit={send}>
      <label>Mitteilung<textarea value={body} onChange={event=>setBody(event.target.value)} rows={4} maxLength={3000} autoFocus placeholder="Was soll die Familie wissen?" required/></label>
      <div className="family-message-options">
        <label><span>Empfänger</span><select value={audience} onChange={event=>setAudience(event.target.value)}><option value="family">Ganze Familie</option><option value="selected">Ausgewählte Mitglieder</option></select></label>
        <label className="family-message-important"><input type="checkbox" checked={important} onChange={event=>setImportant(event.target.checked)}/> Wichtig / anpinnen</label>
      </div>
      {audience==='selected'&&<fieldset className="family-recipient-picker"><legend>Empfänger auswählen</legend>{members.map(member=><label key={member.id}><input type="checkbox" checked={recipientIds.includes(member.id)} onChange={()=>toggleRecipient(member.id)}/><span>{member.display_name||member.username}</span><small>{member.role}</small></label>)}</fieldset>}
      <div className="family-compose-actions"><button type="button" className="secondary compact" onClick={()=>setCompose(false)}>Abbrechen</button><button className="primary compact" type="submit" disabled={busy||!body.trim()}>{busy?'Wird gesendet …':'Senden'}</button></div>
    </form>}

    <div className="filter-chips family-message-filters" aria-label="Mitteilungen filtern">{[['all','Alle'],['unread','Ungelesen'],['family','Familie'],['system','System']].map(([id,label])=><button key={id} className={`chip ${filter===id?'active':''}`} onClick={()=>setFilter(id)}>{label}</button>)}</div>

    <div className="family-message-feed">{visible.length?visible.map(item=><article key={item.id} className={`card family-message-card ${item.unread?'unread':''} ${item.important?'important':''} ${item.source==='manual_message'?'manual':'system'}`} onClick={()=>openItem(item)}>
      <div className="family-message-head"><span className="family-message-source"><Icon name={item.source==='manual_message'?'members':'inbox'}/>{item.source==='manual_message'?'Familie':'System'}</span>{item.important&&<span className="family-message-pin"><Icon name="warning"/> Wichtig</span>}<time>{new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(new Date(item.created_at))}</time></div>
      <div className="family-message-title"><strong>{item.created_by_name||item.source}</strong>{item.unread&&<span className="family-unread-dot" aria-label="Ungelesen"/>}</div>
      {item.title&&item.title!==item.body&&<h2>{item.title}</h2>}
      {item.withdrawn_at?<p className="family-message-withdrawn">Diese Mitteilung wurde zurückgezogen.</p>:<p>{item.body}</p>}
      {item.source==='manual_message'&&item.recipients?.length>0&&<small className="family-message-recipients">An {item.audience==='family'?'die Familie':item.recipients.map(row=>row.display_name).join(', ')}</small>}
      <div className="family-message-actions" onClick={event=>event.stopPropagation()}>{item.source!=='manual_message'&&!item.withdrawn_at&&<><button onClick={()=>act(item,'to_task')}><Icon name="tasks"/> Aufgabe</button><button onClick={()=>act(item,'to_shopping')}><Icon name="shopping"/> Einkauf</button><button onClick={()=>act(item,'dismiss')}><Icon name="check"/> Erledigt</button></>}{item.can_withdraw&&!item.withdrawn_at&&<button className="danger-text" onClick={()=>act(item,'withdraw')}><Icon name="close"/> Zurückziehen</button>}</div>
    </article>):<div className="smart-empty"><Icon name="inbox" size={34}/><strong>Keine Mitteilungen</strong><span>Hier erscheinen Familiennachrichten und Hinweise.</span></div>}</div>
  </section>
}
