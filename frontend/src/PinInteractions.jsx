import {useEffect,useMemo,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {confirmAction} from './feedback';
import './pin-interactions.css';

const REACTIONS=[['thumbs_up','👍'],['heart','❤️'],['joy','😄'],['celebrate','🎉'],['seen','👀']];
const EMPTY={comment_count:0,has_unread_comments:false,reactions:[],can_interact:false,muted:false};
const focusableSelector='button:not([disabled]),a[href],input:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
const unwrap=value=>value?.results||value||[];
const apiPath=value=>{if(!value)return null;const url=new URL(value,location.origin);return url.pathname.replace(/^\/api/,'')+url.search};

function copy(en){return en?{
 react:'React',comment:'Comment',comments:'comments',close:'Close comments',dialog:'Pin comments',write:'Write a comment',send:'Send',sending:'Sending …',loading:'Loading …',failed:'Could not load comments.',retry:'Try again',older:'Load older comments',deleted:'Comment removed',edited:'edited',edit:'Edit',save:'Save',cancel:'Cancel',remove:'Remove',removeConfirm:'Remove this comment?',reply:'Reply',mention:'Mention',mute:'Mute thread',unmute:'Unmute thread',noComments:'No comments yet.',reaction:'Reaction',removeReaction:'Remove reaction',chars:'characters left',picker:'Choose reaction'
}:{
 react:'Reagieren',comment:'Kommentieren',comments:'Kommentare',close:'Kommentare schließen',dialog:'Pin-Kommentare',write:'Kommentar schreiben',send:'Senden',sending:'Wird gesendet …',loading:'Wird geladen …',failed:'Kommentare konnten nicht geladen werden.',retry:'Erneut versuchen',older:'Ältere Kommentare laden',deleted:'Kommentar entfernt',edited:'bearbeitet',edit:'Bearbeiten',save:'Speichern',cancel:'Abbrechen',remove:'Entfernen',removeConfirm:'Diesen Kommentar entfernen?',reply:'Antworten',mention:'Erwähnen',mute:'Thread stummschalten',unmute:'Stummschaltung aufheben',noComments:'Noch keine Kommentare.',reaction:'Reaktion',removeReaction:'Reaktion entfernen',chars:'Zeichen übrig',picker:'Reaktion auswählen'
}}
function reactionLabel(key,en){const labels=en?{thumbs_up:'Works for me',heart:'Heart',joy:'Joy',celebrate:'Celebrate',seen:'Seen'}:{thumbs_up:'Passt',heart:'Herz',joy:'Freude',celebrate:'Feiern',seen:'Gesehen'};return labels[key]||key}
function reactionEmoji(key){return REACTIONS.find(row=>row[0]===key)?.[1]||'•'}

export default function PinInteractionBar({pin,onChange,compact=false}){
 const {i18n}=useTranslation(),en=i18n.language.startsWith('en'),w=copy(en);
 const [summary,setSummary]=useState(pin?.interaction||EMPTY),[picker,setPicker]=useState(false),[thread,setThread]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const triggerRef=useRef(null);
 useEffect(()=>setSummary(pin?.interaction||EMPTY),[pin?.interaction]);
 useEffect(()=>{if(!picker)return;const key=event=>{if(event.key==='Escape'){event.preventDefault();setPicker(false)}};document.addEventListener('keydown',key);return()=>document.removeEventListener('keydown',key)},[picker]);
 if(!pin?.can_interact||summary?.can_interact===false)return null;
 const commit=next=>{setSummary(next||EMPTY);onChange?.(next||EMPTY)};
 async function react(key){if(busy)return;setBusy(true);setError('');const mine=summary.reactions?.find(row=>row.mine),desired=mine?.key===key?null:key;try{commit(await api(`/board/${pin.id}/reaction/`,{method:'PUT',body:JSON.stringify({key:desired})}));setPicker(false)}catch(e){setError(e.message)}finally{setBusy(false)}}
 function openThread(event){triggerRef.current=event.currentTarget;setThread(true);setPicker(false)}
 return <>
  <div className={`pin-interaction-bar ${compact?'compact':''}`}>
   <div className="pin-reaction-summary" aria-label={w.reaction}>
    {(summary.reactions||[]).map(row=><button type="button" key={row.key} className={`pin-reaction-chip ${row.mine?'active':''}`} aria-pressed={row.mine} aria-label={`${reactionLabel(row.key,en)}, ${row.count}`} disabled={busy} onClick={()=>react(row.key)}><span aria-hidden="true">{reactionEmoji(row.key)}</span><span>{row.count}</span></button>)}
    <div className="pin-reaction-picker-wrap"><button type="button" className="pin-interaction-action" aria-expanded={picker} disabled={busy} onClick={()=>setPicker(value=>!value)}><span aria-hidden="true">☺</span><span>{w.react}</span></button>{picker&&<div className="pin-reaction-picker" role="group" aria-label={w.picker}>{REACTIONS.map(([key,emoji])=>{const mine=summary.reactions?.some(row=>row.key===key&&row.mine);return <button type="button" key={key} aria-pressed={mine} aria-label={mine?`${reactionLabel(key,en)} · ${w.removeReaction}`:reactionLabel(key,en)} onClick={()=>react(key)}><span aria-hidden="true">{emoji}</span><span>{reactionLabel(key,en)}</span></button>})}</div>}</div>
   </div>
   <button type="button" className={`pin-interaction-action pin-comment-action ${summary.has_unread_comments?'unread':''}`} onClick={openThread} aria-label={`${w.comment}, ${summary.comment_count||0} ${w.comments}`}><span aria-hidden="true">💬</span><span>{w.comment}</span>{summary.comment_count>0&&<strong>{summary.comment_count}</strong>}{summary.has_unread_comments&&<i aria-hidden="true"/>}</button>
  </div>
  {error&&<small role="alert" className="pin-interaction-error">{error}</small>}
  {thread&&<PinThreadSheet pin={pin} initialSummary={summary} returnFocus={triggerRef.current} onSummary={commit} onClose={()=>setThread(false)}/>} 
 </>
}

function PinThreadSheet({pin,initialSummary,returnFocus,onSummary,onClose}){
 const {i18n}=useTranslation(),en=i18n.language.startsWith('en'),w=copy(en);
 const dialogRef=useRef(null),closeRef=useRef(null),inputRef=useRef(null),reactionForRef=useRef(null),closeHandlerRef=useRef(onClose);
 const [comments,setComments]=useState([]),[mentions,setMentions]=useState([]),[next,setNext]=useState(null),[body,setBody]=useState(''),[mentionIds,setMentionIds]=useState([]),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(''),[editing,setEditing]=useState(null),[editBody,setEditBody]=useState(''),[reactionFor,setReactionFor]=useState(null),[summary,setSummary]=useState(initialSummary||EMPTY);
 reactionForRef.current=reactionFor;closeHandlerRef.current=onClose;
 const mentionQuery=useMemo(()=>{const match=body.match(/(?:^|\s)@([^\s@]*)$/);return match?match[1].toLocaleLowerCase():null},[body]);
 const mentionOptions=useMemo(()=>mentionQuery===null?[]:mentions.filter(row=>!mentionQuery||row.name.toLocaleLowerCase().includes(mentionQuery)).slice(0,6),[mentionQuery,mentions]);
 const updateSummary=nextSummary=>{if(!nextSummary)return;setSummary(nextSummary);onSummary?.(nextSummary)};

 useEffect(()=>{
  const previousOverflow=document.body.style.overflow;document.body.style.overflow='hidden';closeRef.current?.focus();
  const key=event=>{
   if(event.key==='Escape'){event.preventDefault();if(reactionForRef.current){setReactionFor(null);return}closeHandlerRef.current?.();return}
   if(event.key!=='Tab')return;const focusable=[...(dialogRef.current?.querySelectorAll(focusableSelector)||[])];if(!focusable.length){event.preventDefault();dialogRef.current?.focus();return}const first=focusable[0],last=focusable[focusable.length-1],active=document.activeElement;if(event.shiftKey&&(active===first||!dialogRef.current?.contains(active))){event.preventDefault();last.focus()}else if(!event.shiftKey&&(active===last||!dialogRef.current?.contains(active))){event.preventDefault();first.focus()}
  };
  document.addEventListener('keydown',key);return()=>{document.removeEventListener('keydown',key);document.body.style.overflow=previousOverflow;requestAnimationFrame(()=>returnFocus?.isConnected&&returnFocus.focus?.())}
 },[returnFocus]);

 useEffect(()=>{let current=true;(async()=>{setLoading(true);setError('');try{const [thread,targets]=await Promise.all([api(`/board/${pin.id}/comments/`),api(`/board/${pin.id}/mention-targets/`)]);if(!current)return;setComments(unwrap(thread).slice().reverse());setNext(apiPath(thread?.next));setMentions(targets||[]);setSummary(value=>{const seen={...value,has_unread_comments:false};onSummary?.(seen);return seen});setTimeout(()=>inputRef.current?.focus(),0)}catch(e){if(current)setError(e.message||w.failed)}finally{if(current)setLoading(false)}})();return()=>{current=false}},[pin.id]);

 async function loadOlder(){if(!next||busy)return;setBusy(true);try{const data=await api(next);setComments(current=>[...unwrap(data).slice().reverse(),...current]);setNext(apiPath(data?.next))}catch(e){setError(e.message)}finally{setBusy(false)}}
 function chooseMention(row){const replaced=body.replace(/(?:^|\s)@[^\s@]*$/,match=>`${match.startsWith(' ')?' ':''}@${row.name} `);setBody(replaced||`@${row.name} `);setMentionIds(current=>current.includes(row.id)?current:[...current,row.id]);setTimeout(()=>inputRef.current?.focus(),0)}
 function changeBody(value){setBody(value);setMentionIds(current=>current.filter(id=>{const row=mentions.find(item=>item.id===id);return row&&value.includes(`@${row.name}`)}))}
 function reply(comment){const target=mentions.find(row=>row.name===comment.author_name);if(target){setBody(current=>`@${target.name} ${current}`);setMentionIds(current=>current.includes(target.id)?current:[...current,target.id])}else setBody(current=>`@${comment.author_name} ${current}`);setTimeout(()=>inputRef.current?.focus(),0)}
 async function send(event){event.preventDefault();const text=body.trim();if(!text||busy)return;setBusy(true);setError('');try{const row=await api(`/board/${pin.id}/comments/`,{method:'POST',body:JSON.stringify({body:text,client_id:crypto.randomUUID(),mention_membership_ids:mentionIds})});setComments(current=>current.some(item=>item.id===row.id)?current:[...current,row]);setBody('');setMentionIds([]);updateSummary(row.interaction);setTimeout(()=>inputRef.current?.focus(),0)}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function saveEdit(comment){const text=editBody.trim();if(!text||busy)return;setBusy(true);try{const updated=await api(`/board/${pin.id}/comments/${comment.id}/`,{method:'PATCH',body:JSON.stringify({body:text})});setComments(current=>current.map(row=>row.id===updated.id?updated:row));setEditing(null);setEditBody('')}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function removeComment(comment){if(!await confirmAction({title:w.removeConfirm,confirmLabel:w.remove,cancelLabel:w.cancel,danger:true}))return;setBusy(true);try{const result=await api(`/board/${pin.id}/comments/${comment.id}/`,{method:'DELETE'});setComments(current=>current.map(row=>row.id===comment.id?result.comment:row));updateSummary(result.interaction)}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function reactComment(comment,key){if(busy)return;const mine=comment.reactions?.find(row=>row.mine),desired=mine?.key===key?null:key;setBusy(true);try{const updated=await api(`/board/${pin.id}/comments/${comment.id}/reaction/`,{method:'PUT',body:JSON.stringify({key:desired})});setComments(current=>current.map(row=>row.id===updated.id?updated:row));setReactionFor(null)}catch(e){setError(e.message)}finally{setBusy(false)}}
 async function toggleMute(){setBusy(true);try{const updated=await api(`/board/${pin.id}/mute/`,{method:'POST',body:JSON.stringify({muted:!summary.muted})});updateSummary(updated)}catch(e){setError(e.message)}finally{setBusy(false)}}

 return createPortal(<div className="pin-thread-layer" onMouseDown={event=>event.target===event.currentTarget&&onClose?.()}><section ref={dialogRef} className="pin-thread-sheet" role="dialog" aria-modal="true" aria-label={w.dialog} tabIndex={-1}>
  <header className="pin-thread-head"><div><strong>{w.dialog}</strong><small>{summary.comment_count||0} {w.comments}</small></div><div><button type="button" className="pin-thread-quiet" onClick={toggleMute} disabled={busy}>{summary.muted?w.unmute:w.mute}</button><button ref={closeRef} type="button" className="pin-thread-close" onClick={onClose} aria-label={w.close}>×</button></div></header>
  <div className="pin-thread-scroll" aria-live="polite">{next&&<button type="button" className="pin-thread-older" onClick={loadOlder} disabled={busy}>{w.older}</button>}{loading?<p role="status">{w.loading}</p>:comments.length===0?<p className="pin-thread-empty">{w.noComments}</p>:comments.map(comment=><article key={comment.id} className={`pin-comment ${comment.mine?'mine':''}`}>
   <header><strong>{comment.author_name}</strong><time dateTime={comment.created_at}>{new Date(comment.created_at).toLocaleString(en?'en-GB':'de-DE',{dateStyle:'short',timeStyle:'short'})}</time>{comment.edited&&!comment.deleted&&<small>{w.edited}</small>}</header>
   {comment.deleted?<p className="pin-comment-deleted">{w.deleted}</p>:editing===comment.id?<div className="pin-comment-edit"><textarea value={editBody} maxLength={2000} onChange={e=>setEditBody(e.target.value)}/><div><button type="button" onClick={()=>{setEditing(null);setEditBody('')}}>{w.cancel}</button><button type="button" onClick={()=>saveEdit(comment)} disabled={!editBody.trim()||busy}>{w.save}</button></div></div>:<CommentBody text={comment.body}/>}
   {!comment.deleted&&<div className="pin-comment-actions"><button type="button" onClick={()=>reply(comment)}>{w.reply}</button>{comment.can_edit&&<button type="button" onClick={()=>{setEditing(comment.id);setEditBody(comment.body)}}>{w.edit}</button>}{comment.can_delete&&<button type="button" onClick={()=>removeComment(comment)}>{w.remove}</button>}<button type="button" aria-expanded={reactionFor===comment.id} onClick={()=>setReactionFor(value=>value===comment.id?null:comment.id)}>{w.react}</button>{(comment.reactions||[]).map(row=><button type="button" key={row.key} className={row.mine?'active':''} aria-pressed={row.mine} aria-label={`${reactionLabel(row.key,en)}, ${row.count}`} onClick={()=>reactComment(comment,row.key)}><span aria-hidden="true">{reactionEmoji(row.key)}</span> {row.count}</button>)}</div>}
   {reactionFor===comment.id&&<div className="pin-comment-reaction-picker" role="group" aria-label={w.picker}>{REACTIONS.map(([key,emoji])=><button type="button" key={key} aria-label={reactionLabel(key,en)} onClick={()=>reactComment(comment,key)}><span aria-hidden="true">{emoji}</span></button>)}</div>}
  </article>)}</div>
  <form className="pin-thread-compose" onSubmit={send}><label>{w.write}<textarea ref={inputRef} value={body} maxLength={2000} rows={3} onChange={e=>changeBody(e.target.value)} placeholder={w.write}/><small>{2000-body.length} {w.chars}</small></label>{mentionOptions.length>0&&<div className="pin-mention-picker" role="listbox" aria-label={w.mention}>{mentionOptions.map(row=><button type="button" role="option" key={row.id} onClick={()=>chooseMention(row)}>@{row.name}</button>)}</div>}{error&&<p role="alert" className="pin-interaction-error">{error}</p>}<button type="submit" className="pin-thread-send" disabled={busy||!body.trim()}>{busy?w.sending:w.send}</button></form>
 </section></div>,document.body)
}

function CommentBody({text}){const parts=String(text||'').split(/(https?:\/\/[^\s]+)/g);return <p className="pin-comment-body">{parts.map((part,index)=>/^https?:\/\//.test(part)?<a key={index} href={part} target="_blank" rel="noopener noreferrer">{part}</a>:<span key={index}>{part}</span>)}</p>}
