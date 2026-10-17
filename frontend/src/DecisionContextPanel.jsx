import {useEffect,useId,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {useFamilyPermissions} from './family-permissions';
import {SYNC_CHANGED} from './offline-sync-engine';
import {ChoiceField,ErrorSummary,FormActions,FormField,FormSection,FormShell} from './form-primitives';
import './decision-context-panel.css';

const asRows=value=>value?.results||value||[];
const cleanOptions=values=>values.map(value=>value.trim()).filter(Boolean);

function presetsFor(type,en){
 if(type==='shopping_list')return en?[
  {key:'purchase',label:'Plan a purchase',question:'Which option should we buy?',mode:'ranking'},
  {key:'meal',label:'What should we eat?',question:'What should we eat?',mode:'single'},
 ]:[
  {key:'purchase',label:'Anschaffung planen',question:'Welche Option sollen wir anschaffen?',mode:'ranking'},
  {key:'meal',label:'Was wollen wir essen?',question:'Was wollen wir essen?',mode:'single'},
 ];
 if(type==='trip')return en?[
  {key:'destination',label:'Choose destination',question:'Where should we travel?',mode:'ranking'},
  {key:'stay',label:'Choose accommodation',question:'Which accommodation suits us best?',mode:'rating'},
  {key:'activity',label:'Choose activities',question:'What do we want to do there?',mode:'multiple'},
 ]:[
  {key:'destination',label:'Reiseziel abstimmen',question:'Wohin wollen wir reisen?',mode:'ranking'},
  {key:'stay',label:'Unterkunft abstimmen',question:'Welche Unterkunft passt am besten zu uns?',mode:'rating'},
  {key:'activity',label:'Aktivitäten abstimmen',question:'Was wollen wir vor Ort machen?',mode:'multiple'},
 ];
 return [];
}

function winnerLabel(row,en){
 if(!row?.result?.winner)return row?.result?.is_tie?(en?'Tie':'Gleichstand'):'';
 const winner=row.result.winner;
 if(row.result.metric==='average_rank')return `${winner.label} · ${en?'avg. rank':'Ø Rang'} ${winner.value}`;
 if(row.result.metric==='average_score')return `${winner.label} · ${winner.value}/5`;
 return `${winner.label} · ${winner.value} ${en?'votes':'Stimmen'}`;
}

export default function DecisionContextPanel({family,context}){
 const {i18n}=useTranslation();
 const en=i18n.language.startsWith('en');
 const {role}=useFamilyPermissions(family);
 const canCreate=Boolean(role&&role!=='guest');
 const presets=useMemo(()=>presetsFor(context?.type,en),[context?.type,en]);
 const w=en?{
  action:'Vote together',title:'Decide together',hint:'Start a small vote without leaving this context.',loading:'Loading decisions …',failed:'Decisions could not be loaded.',recent:'Votes in this context',open:'Open',closed:'Closed',openDecision:'Open decision',question:'Question',mode:'Voting mode',single:'One choice',multiple:'Several choices',ranking:'Rank options',rating:'Rate 1–5',options:'Options',option:'Option',add:'Add option',remove:'Remove option',create:'Start vote',cancel:'Cancel',saving:'Saving …',created:'Vote created.',apply:'Add winner to shopping list',applied:'Winner added to the shopping list.',tie:'Resolve the tie before transferring a result.',checkForm:'Check the highlighted fields',questionRequired:'Enter a question.',optionRequired:'Enter an option.'
 }:{
  action:'Gemeinsam abstimmen',title:'Gemeinsam entscheiden',hint:'Eine kleine Abstimmung starten, ohne diesen Kontext zu verlassen.',loading:'Abstimmungen werden geladen …',failed:'Abstimmungen konnten nicht geladen werden.',recent:'Abstimmungen in diesem Kontext',open:'Offen',closed:'Geschlossen',openDecision:'Abstimmung öffnen',question:'Frage',mode:'Abstimmungsart',single:'Eine Auswahl',multiple:'Mehrere auswählen',ranking:'Optionen sortieren',rating:'Mit 1–5 bewerten',options:'Optionen',option:'Option',add:'Option hinzufügen',remove:'Option entfernen',create:'Abstimmung starten',cancel:'Abbrechen',saving:'Wird gespeichert …',created:'Abstimmung erstellt.',apply:'Gewinner auf Einkaufsliste',applied:'Gewinner wurde auf die Einkaufsliste übernommen.',tie:'Bei Gleichstand bitte erst ein eindeutiges Ergebnis herstellen.',checkForm:'Bitte prüfe die markierten Felder',questionRequired:'Bitte eine Frage eingeben.',optionRequired:'Bitte eine Option eingeben.'
 };
 const [open,setOpen]=useState(false);
 const [rows,setRows]=useState([]);
 const [loading,setLoading]=useState(false);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [preset,setPreset]=useState(null);
 const [draft,setDraft]=useState({question:'',mode:'single',options:['','']});
 const [busy,setBusy]=useState('');
 const [validationErrors,setValidationErrors]=useState([]);
 const regionId=useId();
 const titleId=useId();
 const questionId=useId();
 const contextId=String(context?.id||'');
 const optionId=index=>`${regionId}-option-${index}`;
 const fieldError=id=>validationErrors.find(item=>item.id===id)?.message||'';

 async function load(){
  if(!open||!family?.id||!contextId)return;
  setLoading(true);setError('');
  try{
   const data=await api(`/decisions/?family=${encodeURIComponent(family.id)}`);
   setRows(asRows(data).filter(row=>String(row.context?.id||'')===contextId&&row.context?.type===context.type));
  }catch(err){setError(err.message||w.failed)}finally{setLoading(false)}
 }
 useEffect(()=>{if(open)void load()},[open,family?.id,contextId,context?.type]);
 if(!canCreate||!presets.length)return null;
 function clearValidation(id){setValidationErrors(old=>old.filter(item=>item.id!==id))}
 function choosePreset(next){setPreset(next.key);setNotice('');setError('');setValidationErrors([]);setDraft({question:next.question,mode:next.mode,options:['','']})}
 function updateOption(index,value){clearValidation(optionId(index));setDraft(old=>({...old,options:old.options.map((item,i)=>i===index?value:item)}))}
 function addOption(){setDraft(old=>old.options.length>=10?old:{...old,options:[...old.options,'']})}
 function removeOption(index){setValidationErrors([]);setDraft(old=>old.options.length<=2?old:{...old,options:old.options.filter((_,i)=>i!==index)})}
 function validateDraft(){
  const next=[];
  if(!draft.question.trim())next.push({id:questionId,label:w.question,message:w.questionRequired});
  draft.options.forEach((value,index)=>{if(!value.trim())next.push({id:optionId(index),label:`${w.option} ${index+1}`,message:w.optionRequired})});
  setValidationErrors(next);
  return next.length===0;
 }
 async function createDecision(event){
  event.preventDefault();if(busy||!validateDraft())return;
  const options=cleanOptions(draft.options);
  setBusy('create');setError('');setNotice('');
  try{
   const created=await api('/decisions/',{method:'POST',body:JSON.stringify({family:family.id,question:draft.question.trim(),mode:draft.mode,anonymous:false,options,context:{type:context.type,id:context.id}})});
   setRows(old=>[created,...old]);setPreset(null);setValidationErrors([]);setNotice(w.created);
  }catch(err){setError(err.message||w.failed)}finally{setBusy('')}
 }
 async function applyWinner(row){
  const winner=row?.result?.winner;if(!winner||context.type!=='shopping_list'||busy)return;
  setBusy(`apply:${row.id}`);setError('');setNotice('');
  try{
   await api('/smart/shopping/quick-add/',{method:'POST',body:JSON.stringify({family:family.id,shopping_list:context.id,name:winner.label,quantity:'',category:'',aisle:'',note:''})});
   window.dispatchEvent(new CustomEvent(SYNC_CHANGED,{detail:{familyId:String(family.id)}}));
   setNotice(w.applied);
  }catch(err){setError(err.message||w.failed)}finally{setBusy('')}
 }
 const modeOptions=[
  {value:'single',label:w.single},
  {value:'multiple',label:w.multiple},
  {value:'ranking',label:w.ranking},
  {value:'rating',label:w.rating},
 ];
 return <section className="decision-context-panel">
  <button type="button" className="secondary decision-context-toggle" onClick={()=>setOpen(value=>!value)} aria-expanded={open} aria-controls={regionId}><Icon name="check"/><span>{w.action}</span><span className="decision-context-toggle__indicator" aria-hidden="true">{open?'−':'+'}</span></button>
  {open&&<div id={regionId} className="decision-context-panel__body" role="region" aria-labelledby={titleId} aria-busy={loading||Boolean(busy)}>
   <header className="decision-context-panel__intro"><strong id={titleId}>{w.title}</strong><p>{w.hint}</p></header>
   {!preset&&<div className="decision-context-presets" role="group" aria-label={w.title}>{presets.map(item=><button type="button" className="secondary" key={item.key} onClick={()=>choosePreset(item)}>{item.label}</button>)}</div>}
   {preset&&<FormShell className="decision-context-form" onSubmit={createDecision} noValidate>
    <ErrorSummary errors={validationErrors} title={w.checkForm}/>
    <FormField id={questionId} label={w.question} required error={fieldError(questionId)}><input maxLength={500} value={draft.question} onChange={event=>{clearValidation(questionId);setDraft(old=>({...old,question:event.target.value}))}}/></FormField>
    <ChoiceField legend={w.mode} options={modeOptions} value={draft.mode} onChange={value=>setDraft(old=>({...old,mode:value}))}/>
    <FormSection legend={w.options}>{draft.options.map((value,index)=><div className="decision-context-option" key={index}><FormField id={optionId(index)} label={`${w.option} ${index+1}`} required error={fieldError(optionId(index))}><input maxLength={240} value={value} onChange={event=>updateOption(index,event.target.value)}/></FormField>{draft.options.length>2&&<button type="button" className="ghost icon-btn" aria-label={`${w.remove} ${index+1}`} onClick={()=>removeOption(index)}><Icon name="delete"/></button>}</div>)}{draft.options.length<10&&<button type="button" className="secondary compact decision-context-add-option" onClick={addOption}><Icon name="plus"/>{w.add}</button>}</FormSection>
    <FormActions><button type="button" className="secondary" onClick={()=>{setPreset(null);setValidationErrors([])}} disabled={busy==='create'}>{w.cancel}</button><button type="submit" className="primary" disabled={busy==='create'}>{busy==='create'?w.saving:w.create}</button></FormActions>
   </FormShell>}
   {error&&<p className="decision-context-message is-error" role="alert">{error}</p>}{notice&&<p className="decision-context-message" role="status">{notice}</p>}
   {loading&&<p className="decision-context-muted" role="status">{w.loading}</p>}
   {!loading&&rows.length>0&&<div className="decision-context-recent"><strong>{w.recent}</strong>{rows.slice(0,3).map(row=><article key={row.id}><div><span className={`decision-context-state ${row.is_open?'is-open':''}`}>{row.is_open?w.open:w.closed}</span><b>{row.question}</b>{winnerLabel(row,en)&&<small>{winnerLabel(row,en)}</small>}</div><div className="decision-context-row-actions"><a className="secondary compact" href={`/?page=decisions&decision=${encodeURIComponent(row.id)}`}>{w.openDecision}</a>{context.type==='shopping_list'&&!row.is_open&&row.result?.winner&&<button type="button" className="primary compact" disabled={busy===`apply:${row.id}`} onClick={()=>applyWinner(row)}><Icon name="plus"/>{w.apply}</button>}{context.type==='shopping_list'&&!row.is_open&&row.result?.is_tie&&<small>{w.tie}</small>}</div></article>)}</div>}
  </div>}
 </section>;
}
