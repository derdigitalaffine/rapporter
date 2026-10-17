import ContextActionButton from './ContextActionButton';
import {useEffect,useId,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {useFamilyPermissions} from './family-permissions';
import {ChoiceField,ErrorSummary,FormActions,FormField,FormRow,FormSection,FormShell,ProgressiveFieldGroup} from './form-primitives';
import {decisionContextClearedHref,decisionContextFromSearch,decisionPresetDraft} from './decision-context';
import {decisionResultState,decisionUrgency,filterDecisions,hasDecisionParticipation,sortDecisions} from './decision-presentation';
import {SYNC_CHANGED} from './offline-sync-engine';
import './decisions.css';

const emptyDraft=()=>({question:'',mode:'single',anonymous:false,closes_at:'',options:['','']});
const asRows=data=>data?.results||data||[];
const cleanOptions=values=>values.map(value=>value.trim()).filter(Boolean);

function formatDeadline(value,locale){
 if(!value)return'';
 try{return new Intl.DateTimeFormat(locale,{dateStyle:'medium',timeStyle:'short'}).format(new Date(value))}catch{return String(value)}
}

export default function DecisionsHub({family,onBack}){
 const {i18n}=useTranslation();
 const en=i18n.language.startsWith('en');
 const locale=en?'en-GB':'de-DE';
 const routeContext=decisionContextFromSearch(location.search);
 const routedDraft=decisionPresetDraft(location.search,en);
 const w=en?{
  title:'Decisions',hint:'Make family choices together. Open questions come first; finished decisions stay available as results.',back:'Back',newDecision:'New decision',question:'Question',mode:'Voting mode',single:'One option',multiple:'Several options',ranking:'Rank options',rating:'Rate 1–5',anonymous:'Hide voter identities in results',deadline:'Deadline',option:'Option',options:'Options',optionsHint:'Add at least two clear choices.',addOption:'Add option',removeOption:'Remove option',create:'Create decision',cancel:'Cancel',loading:'Loading decisions …',empty:'No decisions yet.',emptyHint:'Create a decision when the family needs a clear choice.',failed:'Decisions could not be loaded.',retry:'Try again',votes:'votes',anonymousHint:'Voter identities stay hidden.',submitVote:'Save vote',retract:'Clear my vote',close:'Close decision',closed:'Closed',open:'Open',until:'Open until',context:'Open context',contextCreate:'This decision stays linked to the context you came from.',saving:'Saving …',created:'Decision created.',voteSaved:'Vote saved.',closedDone:'Decision closed.',moveUp:'Move up',moveDown:'Move down',rank:'Rank',avgRank:'avg. rank',ratingValue:'Rating',avgRating:'average',modeHintRanking:'Put all options in your preferred order.',modeHintRating:'Rate one or more options from 1 to 5.',apply:'Add winner to shopping list',applied:'Winner added to the shopping list.',tie:'Tie: choose a clear result before transferring it.',filterOpen:'Open',filterClosed:'Finished',filterAll:'All',filterHint:'Open decisions with the nearest deadline appear first. Nothing is changed automatically.',noOpen:'No open decisions.',noClosed:'No finished decisions yet.',showFinished:'Show finished decisions',showOpen:'Show open decisions',openSummary:'open',closedSummary:'finished',endsSoon:'Ends within 24 hours',yourVoteSaved:'Your vote is saved. You can still change it while the decision is open.',yourVoteOpen:'Your vote is still open.',readOnly:'Read-only for you.',participantsOne:'1 person voted',participantsMany:'{{count}} people voted',result:'Result',resultWinner:'Decision',resultTie:'No unique result — tie.',resultClosed:'Decision finished without a unique winner.',currentResult:'Current result',advanced:'More settings',advancedHint:'Optional: deadline and anonymous results',checkForm:'Check the highlighted fields',questionRequired:'Enter a question.',optionRequired:'Add at least two non-empty options.',singleHint:'Everyone chooses one option.',multipleHint:'Everyone may choose several options.',rankingHint:'Everyone orders all options.',ratingHint:'Everyone rates options independently from 1 to 5.',readOnlyHub:'You can view family decisions here. Creating and voting require write access.'
 }:{
  title:'Entscheidungen',hint:'Gemeinsam klar entscheiden. Offene Fragen stehen vorn, abgeschlossene Entscheidungen bleiben als Ergebnis erhalten.',back:'Zurück',newDecision:'Neue Entscheidung',question:'Frage',mode:'Abstimmungsart',single:'Eine Option',multiple:'Mehrere Optionen',ranking:'Optionen sortieren',rating:'Mit 1–5 bewerten',anonymous:'Identitäten der Abstimmenden im Ergebnis ausblenden',deadline:'Ende',option:'Option',options:'Optionen',optionsHint:'Mindestens zwei klare Auswahlmöglichkeiten angeben.',addOption:'Option hinzufügen',removeOption:'Option entfernen',create:'Entscheidung erstellen',cancel:'Abbrechen',loading:'Entscheidungen werden geladen …',empty:'Noch keine Entscheidungen.',emptyHint:'Lege eine Entscheidung an, wenn die Familie eine klare Auswahl treffen soll.',failed:'Entscheidungen konnten nicht geladen werden.',retry:'Erneut versuchen',votes:'Stimmen',anonymousHint:'Identitäten der Abstimmenden bleiben verborgen.',submitVote:'Stimme speichern',retract:'Meine Stimme löschen',close:'Entscheidung schließen',closed:'Abgeschlossen',open:'Offen',until:'Offen bis',context:'Kontext öffnen',contextCreate:'Diese Entscheidung bleibt mit dem Ausgangskontext verknüpft.',saving:'Wird gespeichert …',created:'Entscheidung erstellt.',voteSaved:'Stimme gespeichert.',closedDone:'Entscheidung geschlossen.',moveUp:'Nach oben',moveDown:'Nach unten',rank:'Rang',avgRank:'Ø Rang',ratingValue:'Bewertung',avgRating:'Durchschnitt',modeHintRanking:'Bringe alle Optionen in deine bevorzugte Reihenfolge.',modeHintRating:'Bewerte eine oder mehrere Optionen von 1 bis 5.',apply:'Gewinner auf Einkaufsliste',applied:'Gewinner wurde auf die Einkaufsliste übernommen.',tie:'Gleichstand: Bitte erst ein eindeutiges Ergebnis herstellen.',filterOpen:'Offen',filterClosed:'Abgeschlossen',filterAll:'Alle',filterHint:'Offene Entscheidungen mit der nächsten Frist erscheinen zuerst. Es wird nichts automatisch verändert.',noOpen:'Keine offenen Entscheidungen.',noClosed:'Noch keine abgeschlossenen Entscheidungen.',showFinished:'Abgeschlossene anzeigen',showOpen:'Offene anzeigen',openSummary:'offen',closedSummary:'abgeschlossen',endsSoon:'Endet innerhalb von 24 Stunden',yourVoteSaved:'Deine Stimme ist gespeichert. Solange die Entscheidung offen ist, kannst du sie noch ändern.',yourVoteOpen:'Deine Stimme ist noch offen.',readOnly:'Für dich nur lesbar.',participantsOne:'1 Person hat abgestimmt',participantsMany:'{{count}} Personen haben abgestimmt',result:'Ergebnis',resultWinner:'Entscheidung',resultTie:'Kein eindeutiges Ergebnis – Gleichstand.',resultClosed:'Entscheidung ohne eindeutigen Gewinner abgeschlossen.',currentResult:'Aktueller Stand',advanced:'Weitere Einstellungen',advancedHint:'Optional: Ende und anonymes Ergebnis',checkForm:'Bitte prüfe die markierten Felder',questionRequired:'Bitte eine Frage eingeben.',optionRequired:'Bitte mindestens zwei nicht leere Optionen angeben.',singleHint:'Jede Person wählt genau eine Option.',multipleHint:'Jede Person darf mehrere Optionen wählen.',rankingHint:'Alle Optionen werden in eine Reihenfolge gebracht.',ratingHint:'Optionen werden unabhängig mit 1 bis 5 bewertet.',readOnlyHub:'Du kannst Familienentscheidungen ansehen. Erstellen und Abstimmen benötigen Schreibrechte.'
 };
 const familyId=family?.id;
 const {role}=useFamilyPermissions(family);
 const canCreate=Boolean(role&&role!=='guest');
 const questionId=useId();
 const optionsId=useId();
 const [rows,setRows]=useState([]);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [creating,setCreating]=useState(Boolean(routedDraft));
 const [draft,setDraft]=useState(()=>routedDraft||emptyDraft());
 const [busy,setBusy]=useState('');
 const [choices,setChoices]=useState({});
 const [ratings,setRatings]=useState({});
 const [filter,setFilter]=useState('open');
 const [validationErrors,setValidationErrors]=useState([]);

 async function load(){
  if(!familyId)return;
  setLoading(true);setError('');
  try{const data=await api(`/decisions/?family=${encodeURIComponent(familyId)}`);setRows(asRows(data))}
  catch(e){setError(e.message||w.failed)}
  finally{setLoading(false)}
 }
 useEffect(()=>{setRows([]);setChoices({});setRatings({});setCreating(Boolean(routedDraft));setDraft(routedDraft||emptyDraft());setValidationErrors([]);setFilter('open');setNotice('');void load()},[familyId]);
 useEffect(()=>{
  const target=new URLSearchParams(location.search).get('decision');
  if(!target||!rows.length)return;
  const targetRow=rows.find(row=>String(row.id)===String(target));
  if(targetRow&&!targetRow.is_open&&filter==='open'){setFilter('all');return}
  requestAnimationFrame(()=>document.getElementById(`decision-${target}`)?.focus({preventScroll:false}));
 },[rows,filter]);
 useEffect(()=>{if(creating)requestAnimationFrame(()=>document.getElementById(questionId)?.focus({preventScroll:false}))},[creating,questionId]);

 const openCount=useMemo(()=>rows.filter(row=>row.is_open).length,[rows]);
 const closedCount=rows.length-openCount;
 const visibleRows=useMemo(()=>filterDecisions(sortDecisions(rows),filter),[rows,filter]);
 const modeLabels={single:w.single,multiple:w.multiple,ranking:w.ranking,rating:w.rating};
 const modeOptions=[
  {value:'single',label:w.single,description:w.singleHint},
  {value:'multiple',label:w.multiple,description:w.multipleHint},
  {value:'ranking',label:w.ranking,description:w.rankingHint},
  {value:'rating',label:w.rating,description:w.ratingHint},
 ];
 const fieldError=id=>validationErrors.find(item=>item.id===id)?.message||'';
 const optionId=index=>`${optionsId}-${index}`;

 function clearValidation(id){setValidationErrors(old=>old.filter(item=>item.id!==id))}
 function updateOption(index,value){clearValidation(optionId(index));setDraft(old=>({...old,options:old.options.map((item,i)=>i===index?value:item)}))}
 function addOption(){setDraft(old=>old.options.length>=10?old:{...old,options:[...old.options,'']})}
 function removeOption(index){setValidationErrors([]);setDraft(old=>old.options.length<=2?old:{...old,options:old.options.filter((_,i)=>i!==index)})}
 function clearContextRoute(decision=null){if(!routeContext)return;history.replaceState({...history.state,page:'decisions'},'',decisionContextClearedHref(location.href,decision))}
 function cancelCreate(){setCreating(false);setDraft(emptyDraft());setValidationErrors([]);clearContextRoute()}
 function startCreate(){setFilter('open');setCreating(true);setError('');setNotice('');setValidationErrors([])}
 function validateDraft(){
  const next=[];
  if(!draft.question.trim())next.push({id:questionId,label:w.question,message:w.questionRequired});
  let missing=Math.max(0,2-cleanOptions(draft.options).length);
  for(let index=0;index<draft.options.length&&missing>0;index+=1){if(!draft.options[index].trim()){next.push({id:optionId(index),label:`${w.option} ${index+1}`,message:w.optionRequired});missing-=1}}
  setValidationErrors(next);
  return next.length===0;
 }
 async function createDecision(e){
  e.preventDefault();if(busy||!validateDraft())return;
  setBusy('create');setError('');setNotice('');
  try{
   const payload={family:familyId,question:draft.question.trim(),mode:draft.mode,anonymous:draft.anonymous,options:cleanOptions(draft.options)};
   if(routeContext)payload.context=routeContext;
   if(draft.closes_at)payload.closes_at=new Date(draft.closes_at).toISOString();
   const created=await api('/decisions/',{method:'POST',body:JSON.stringify(payload)});
   setRows(old=>[created,...old]);setDraft(emptyDraft());setValidationErrors([]);setCreating(false);setFilter('open');clearContextRoute(created.id);setNotice(w.created);
  }catch(e){setError(e.message||w.failed)}finally{setBusy('')}
 }
 function selectedFor(row){return choices[row.id]??row.my_option_ids??[]}
 function rankingFor(row){const current=choices[row.id]??row.my_option_ids??[];return current.length===row.options.length?current:row.options.map(option=>option.id)}
 function ratingsFor(row){if(ratings[row.id])return ratings[row.id];return Object.fromEntries(row.options.filter(option=>option.my_score!=null).map(option=>[option.id,option.my_score]))}
 function choose(row,optionIdValue,checked){setChoices(old=>{const current=old[row.id]??row.my_option_ids??[];const next=row.mode==='single'?(checked?[optionIdValue]:[]):checked?[...new Set([...current,optionIdValue])]:current.filter(id=>id!==optionIdValue);return {...old,[row.id]:next}})}
 function moveRank(row,optionIdValue,delta){setChoices(old=>{const current=[...rankingFor(row)];const index=current.indexOf(optionIdValue),target=index+delta;if(index<0||target<0||target>=current.length)return old;[current[index],current[target]]=[current[target],current[index]];return {...old,[row.id]:current}})}
 function rate(row,optionIdValue,score){setRatings(old=>({...old,[row.id]:{...ratingsFor(row),[optionIdValue]:score}}))}
 async function saveVote(row,{clear=false}={}){if(busy)return;setBusy(`vote:${row.id}`);setError('');setNotice('');try{let payload={family:familyId};if(row.mode==='rating'){payload.ratings=clear?[]:Object.entries(ratingsFor(row)).map(([option_id,score])=>({option_id,score}))}else if(row.mode==='ranking'){payload.option_ids=clear?[]:rankingFor(row)}else{payload.option_ids=clear?[]:selectedFor(row)}const updated=await api(`/decisions/${row.id}/vote/`,{method:'POST',body:JSON.stringify(payload)});setRows(old=>old.map(item=>item.id===row.id?updated:item));setChoices(old=>{const next={...old};delete next[row.id];return next});setRatings(old=>{const next={...old};delete next[row.id];return next});setNotice(w.voteSaved)}catch(e){setError(e.message||w.failed)}finally{setBusy('')}}
 async function closeDecision(row){if(busy)return;setBusy(`close:${row.id}`);setError('');setNotice('');try{const updated=await api(`/decisions/${row.id}/close/`,{method:'POST',body:JSON.stringify({family:familyId})});setRows(old=>old.map(item=>item.id===row.id?updated:item));setNotice(w.closedDone)}catch(e){setError(e.message||w.failed)}finally{setBusy('')}}
 async function applyWinner(row){const winner=row?.result?.winner;if(busy||row?.context?.type!=='shopping_list'||!row?.context?.id||!winner)return;setBusy(`apply:${row.id}`);setError('');setNotice('');try{await api('/smart/shopping/quick-add/',{method:'POST',body:JSON.stringify({family:familyId,shopping_list:row.context.id,name:winner.label,quantity:'',category:'',aisle:'',note:''})});window.dispatchEvent(new CustomEvent(SYNC_CHANGED,{detail:{familyId:String(familyId)}}));setNotice(w.applied)}catch(e){setError(e.message||w.failed)}finally{setBusy('')}}
 function optionResult(row,option){if(row.mode==='ranking'&&option.average_rank!=null)return `${w.avgRank} ${option.average_rank}`;if(row.mode==='rating'&&option.average_score!=null)return `${w.avgRating} ${option.average_score}/5`;return `${option.votes} ${w.votes}`}
 function voterNames(row,option){if(row.anonymous||!option.voters?.length)return'';return ` · ${option.voters.map(voter=>voter.name).join(', ')}`}
 function participants(row){const count=Number(row.total_voters||0);return count===1?w.participantsOne:w.participantsMany.replace('{{count}}',String(count))}
 function resultSummary(row){
  const state=decisionResultState(row);
  if(state==='tie')return {label:w.resultTie,detail:''};
  const winner=row?.result?.winner;
  if(state!=='winner'||!winner)return {label:w.resultClosed,detail:''};
  let detail='';
  if(row.result.metric==='average_rank'&&winner.value!=null)detail=`${w.avgRank} ${winner.value}`;
  else if(row.result.metric==='average_score'&&winner.value!=null)detail=`${w.avgRating} ${winner.value}/5`;
  else if(winner.value!=null)detail=`${winner.value} ${w.votes}`;
  return {label:`${w.resultWinner}: ${winner.label}`,detail};
 }
 function filterButton(value,label,count){return <button type="button" className={`secondary compact decision-filter-button ${filter===value?'is-active':''}`} aria-pressed={filter===value} onClick={()=>setFilter(value)}><span>{label}</span>{count!=null&&<span className="decision-filter-count" aria-hidden="true">{count}</span>}</button>}

 return <section className="decisions-hub">
  <header className="page-head decision-page-head"><button type="button" className="ghost icon-button icon-btn" aria-label={w.back} onClick={onBack}><Icon name="back"/></button><div><h1>{w.title}</h1><p>{w.hint}</p></div></header>
  <section className="decision-overview" aria-label={w.title}>
   <div className="decision-overview-copy"><strong>{openCount} {w.openSummary}</strong><span aria-hidden="true">·</span><span>{closedCount} {w.closedSummary}</span></div>
   {canCreate?<button type="button" className="primary decision-new" onClick={startCreate}><Icon name="plus"/>{w.newDecision}</button>:<p className="decision-readonly-note"><Icon name="lock"/>{w.readOnlyHub}</p>}
  </section>

  {creating&&<FormShell className="card decision-create" onSubmit={createDecision} noValidate aria-busy={busy==='create'}>
   <div className="decision-form-head"><div><span className="decision-kicker">{w.newDecision}</span><h2>{draft.question.trim()||w.newDecision}</h2></div><button type="button" className="ghost icon-button icon-btn" aria-label={w.cancel} onClick={cancelCreate}><Icon name="close"/></button></div>
   {routeContext&&<p className="decision-context-create"><Icon name="link"/> {w.contextCreate}</p>}
   <ErrorSummary errors={validationErrors} title={w.checkForm}/>
   <FormField id={questionId} label={w.question} required error={fieldError(questionId)}><textarea maxLength={500} rows={3} value={draft.question} onChange={e=>{clearValidation(questionId);setDraft(old=>({...old,question:e.target.value}))}}/></FormField>
   <ChoiceField legend={w.mode} options={modeOptions} value={draft.mode} onChange={value=>setDraft(old=>({...old,mode:value}))}/>
   <FormSection legend={w.options} description={w.optionsHint}>{draft.options.map((value,index)=><div className="decision-option-edit" key={index}><FormField id={optionId(index)} label={`${w.option} ${index+1}`} required={index<2} error={fieldError(optionId(index))}><input maxLength={240} value={value} onChange={e=>updateOption(index,e.target.value)}/></FormField>{draft.options.length>2&&<button type="button" className="ghost icon-button icon-btn" aria-label={`${w.removeOption} ${index+1}`} onClick={()=>removeOption(index)}><Icon name="delete"/></button>}</div>)}{draft.options.length<10&&<button type="button" className="secondary compact decision-add-option" onClick={addOption}><Icon name="plus"/>{w.addOption}</button>}</FormSection>
   <ProgressiveFieldGroup label={w.advanced} summary={w.advancedHint}><FormRow><FormField label={w.deadline}><input type="datetime-local" value={draft.closes_at} onChange={e=>setDraft(old=>({...old,closes_at:e.target.value}))}/></FormField><label className="decision-check"><input type="checkbox" checked={draft.anonymous} onChange={e=>setDraft(old=>({...old,anonymous:e.target.checked}))}/><span>{w.anonymous}</span></label></FormRow></ProgressiveFieldGroup>
   <FormActions><button type="button" className="secondary" onClick={cancelCreate} disabled={busy==='create'}>{w.cancel}</button><button type="submit" className="primary" disabled={busy==='create'}>{busy==='create'?w.saving:w.create}</button></FormActions>
  </FormShell>}

  {error&&<div className="card decision-alert" role="alert"><span>{error}</span>{!loading&&<button type="button" className="secondary compact" onClick={load}>{w.retry}</button>}</div>}
  {notice&&<div className="decision-notice" role="status">{notice}</div>}
  {loading&&<div className="card decision-state-panel" role="status"><span className="decision-state-dot" aria-hidden="true"/><span>{w.loading}</span></div>}

  {!loading&&rows.length>0&&<section className="decision-toolbar" aria-label={w.title}><div className="decision-filters" role="group" aria-label={w.title}>{filterButton('open',w.filterOpen,openCount)}{filterButton('closed',w.filterClosed,closedCount)}{filterButton('all',w.filterAll,rows.length)}</div><p>{w.filterHint}</p></section>}

  {!loading&&!rows.length&&!error&&<div className="card smart-empty decision-empty"><Icon name="check" size={32}/><strong>{w.empty}</strong><p>{w.emptyHint}</p>{canCreate&&<button type="button" className="secondary" onClick={startCreate}>{w.newDecision}</button>}</div>}
  {!loading&&rows.length>0&&!visibleRows.length&&<div className="card decision-filter-empty"><strong>{filter==='closed'?w.noClosed:w.noOpen}</strong><button type="button" className="secondary compact" onClick={()=>setFilter(filter==='closed'?'open':'closed')}>{filter==='closed'?w.showOpen:w.showFinished}</button></div>}

  <div className="decision-list">{visibleRows.map(row=>{
   const selected=selectedFor(row);
   const ranking=rankingFor(row);
   const rowRatings=ratingsFor(row);
   const hasMine=hasDecisionParticipation(row);
   const interactive=Boolean(row.is_open&&row.can_vote);
   const urgency=decisionUrgency(row);
   const summary=!row.is_open?resultSummary(row):null;
   const cardBusy=busy===`vote:${row.id}`||busy===`close:${row.id}`||busy===`apply:${row.id}`;
   return <article className={`card decision-card ${row.is_open?'is-open':'is-closed'} ${urgency==='soon'||urgency==='due'?'is-attention':''}`} id={`decision-${row.id}`} key={row.id} tabIndex={-1} aria-busy={cardBusy}>
    <header className="decision-card-head"><div className="decision-card-title"><div className="decision-state-row"><span className={`decision-state ${row.is_open?'is-open':'is-closed'}`}>{row.is_open?w.open:w.closed}</span><span className="decision-mode">{modeLabels[row.mode]||row.mode}</span>{row.is_open&&(urgency==='soon'||urgency==='due')&&<span className="decision-attention"><Icon name="warning"/>{w.endsSoon}</span>}</div><h2>{row.question}</h2><div className="decision-card-meta"><span>{participants(row)}</span>{row.closes_at&&<span>{w.until}: {formatDeadline(row.closes_at,locale)}</span>}</div></div></header>
    <div className="decision-card-links">{row.context&&<a className="decision-context" href={row.context.deep_link||'#'}><Icon name="link"/>{w.context}</a>}</div>

    {!row.is_open&&<section className={`decision-result-summary ${row.result?.is_tie?'is-tie':''}`} aria-label={w.result}><span className="decision-kicker">{w.result}</span><strong>{summary.label}</strong>{summary.detail&&<small>{summary.detail}</small>}</section>}
    {row.is_open&&<p className={`decision-participation ${hasMine?'is-saved':''}`}><Icon name={hasMine?'check':'info'}/>{hasMine?w.yourVoteSaved:interactive?w.yourVoteOpen:w.readOnly}</p>}

    {interactive&&row.mode==='ranking'?<fieldset className="decision-vote-options decision-ranking" disabled={cardBusy}><legend className="sr-only">{row.question}</legend><p className="decision-mode-hint">{w.modeHintRanking}</p>{ranking.map((optionIdValue,index)=>{const option=row.options.find(item=>item.id===optionIdValue);if(!option)return null;return <div className="decision-ranking-row" key={option.id}><span className="decision-rank-number" aria-label={`${w.rank} ${index+1}`}>{index+1}</span><span className="decision-option-copy"><strong>{option.label}</strong><small>{optionResult(row,option)}{voterNames(row,option)}</small></span><div className="decision-rank-actions"><button type="button" className="secondary icon-btn" disabled={cardBusy||index===0} aria-label={`${w.moveUp}: ${option.label}`} onClick={()=>moveRank(row,option.id,-1)}>↑</button><button type="button" className="secondary icon-btn" disabled={cardBusy||index===ranking.length-1} aria-label={`${w.moveDown}: ${option.label}`} onClick={()=>moveRank(row,option.id,1)}>↓</button></div></div>})}</fieldset>:interactive&&row.mode==='rating'?<fieldset className="decision-vote-options decision-rating" disabled={cardBusy}><legend className="sr-only">{row.question}</legend><p className="decision-mode-hint">{w.modeHintRating}</p>{row.options.map(option=><div className="decision-rating-row" key={option.id}><span className="decision-option-copy"><strong>{option.label}</strong><small>{optionResult(row,option)}{voterNames(row,option)}</small></span><div className="decision-rating-scale" role="radiogroup" aria-label={`${w.ratingValue}: ${option.label}`}>{[1,2,3,4,5].map(score=><label className={Number(rowRatings[option.id])===score?'is-selected':''} key={score}><input type="radio" name={`decision-${row.id}-${option.id}`} checked={Number(rowRatings[option.id])===score} onChange={()=>rate(row,option.id,score)}/><span>{score}</span></label>)}</div></div>)}</fieldset>:interactive?<fieldset className="decision-vote-options" disabled={cardBusy}><legend className="sr-only">{row.question}</legend>{row.options.map(option=>{const checked=selected.includes(option.id);return <label className={`decision-vote-option ${checked?'is-selected':''}`} key={option.id}><input type={row.mode==='single'?'radio':'checkbox'} name={`decision-${row.id}`} checked={checked} onChange={e=>choose(row,option.id,e.target.checked)}/><span className="decision-option-copy"><strong>{option.label}</strong><small>{optionResult(row,option)}{voterNames(row,option)}</small></span></label>})}</fieldset>:<section className="decision-results-list" aria-label={w.currentResult}>{row.options.map(option=><div className="decision-result-row" key={option.id}><strong>{option.label}</strong><small>{optionResult(row,option)}{voterNames(row,option)}</small></div>)}</section>}

    {row.anonymous&&<p className="decision-anonymous"><Icon name="lock"/>{w.anonymousHint}</p>}
    <footer className="decision-card-footer"><div className="decision-secondary-tools"><ContextActionButton family={family} context={{type:'decision',id:row.id}} title={row.question}/></div><div className="decision-actions">{interactive&&<><button type="button" className="primary compact" onClick={()=>saveVote(row)} disabled={cardBusy}>{busy===`vote:${row.id}`?w.saving:w.submitVote}</button>{hasMine&&<button type="button" className="secondary compact" onClick={()=>saveVote(row,{clear:true})} disabled={cardBusy}>{w.retract}</button>}</>}{row.can_close&&row.is_open&&<button type="button" className="ghost ghost-danger compact" onClick={()=>closeDecision(row)} disabled={cardBusy}>{w.close}</button>}{!row.is_open&&row.context?.type==='shopping_list'&&row.result?.winner&&<button type="button" className="primary compact" onClick={()=>applyWinner(row)} disabled={cardBusy}><Icon name="plus"/>{w.apply}</button>}{!row.is_open&&row.context?.type==='shopping_list'&&row.result?.is_tie&&<small className="decision-tie-note">{w.tie}</small>}</div></footer>
   </article>
  })}</div>
 </section>
}
