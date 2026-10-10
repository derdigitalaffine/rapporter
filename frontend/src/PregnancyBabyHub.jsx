import {useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {confirmAction,toast} from './feedback';
import BabyPrivateMediaField from './BabyPrivateMediaField';
import BabyCarePanel from './BabyCarePanel';
import BabyReportPanel from './BabyReportPanel';
import BabyPreventivePanel from './BabyPreventivePanel';
import './baby-i18n';
import './pregnancy-baby.css';

const isoNow=()=>new Date().toISOString();
const dateToday=()=>new Date().toISOString().slice(0,10);
const uid=()=>crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`;

function Panel({children,className=''}){
 return <section className={`card baby-panel ${className}`}>{children}</section>;
}
function Toggle({checked,onChange,label,hint,disabled=false}){
 return <label className="baby-toggle"><input type="checkbox" checked={checked} disabled={disabled} onChange={e=>onChange(e.target.checked)}/><span><strong>{label}</strong>{hint&&<small>{hint}</small>}</span></label>;
}
function TabButton({active,onClick,children}){
 return <button className={active?'active':''} onClick={onClick}>{children}</button>;
}

export default function PregnancyBabyHub({family,onBack,onModuleChange}){
 const {t,i18n}=useTranslation();
 const [module,setModule]=useState(null);
 const [pregnancies,setPregnancies]=useState([]);
 const [babies,setBabies]=useState([]);
 const [selectedBaby,setSelectedBaby]=useState('');
 const [tab,setTab]=useState('pregnancy');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const activePregnancy=pregnancies.find(row=>row.status==='active');
 const baby=babies.find(row=>String(row.id)===String(selectedBaby))||babies[0];
 const permissions=module?.permissions||{};
 const canPregnancy=!!permissions.can_view_pregnancy;
 const canCare=!!permissions.can_log_care;
 const canGrowth=!!permissions.can_view_growth_development;
 const canManageChild=!!permissions.is_guardian;

 async function loadModule(){
  if(!family)return null;
  const row=await api(`/baby/module/?family=${encodeURIComponent(family.id)}`);
  setModule(row);onModuleChange?.(row);return row;
 }
 async function loadPrivate(row=module){
  if(!family||!row?.enabled||!row?.authorized)return;
  const jobs=[];
  if(row.permissions?.can_view_pregnancy)jobs.push(api(`/baby/pregnancies/?family=${encodeURIComponent(family.id)}`).then(data=>setPregnancies(data.pregnancies||[])));
  if(row.permissions?.can_log_care||row.permissions?.can_view_growth_development)jobs.push(api(`/baby/profiles/?family=${encodeURIComponent(family.id)}`).then(data=>{setBabies(data.babies||[]);setSelectedBaby(value=>value||(data.babies?.[0]?.id||''))}));
  await Promise.all(jobs);
 }
 useEffect(()=>{let live=true;(async()=>{setError('');try{const row=await loadModule();if(live)await loadPrivate(row)}catch(error){if(live)setError(error.message||t('babyUi.error'))}})();return()=>{live=false}},[family?.id]);
 async function refresh(){const row=await loadModule();await loadPrivate(row)}
 async function action(fn,success=t('babyUi.saved')){
  setBusy(true);setError('');
  try{const result=await fn();toast(success,{type:'success'});return result}
  catch(error){setError(error.message||t('babyUi.error'));toast(error.message||t('babyUi.error'),{type:'error'});throw error}
  finally{setBusy(false)}
 }
 if(!family)return null;
 if(!module)return <div className="smart-empty"><Icon name="refresh"/><strong>{t('babyUi.loading')}</strong></div>;
 return <div className="baby-page">
  <div className="page-head"><button className="back-button" onClick={onBack} aria-label={t('back')}><Icon name="back"/></button><div className="grow"><small>{t('babyUi.privacy')}</small><h1>{t('babyUi.title')}</h1></div><span className="baby-private-pill"><Icon name="lock" size={13}/>{t('babyUi.careCircle')}</span></div>
  {error&&<div className="integration-notice" role="alert"><Icon name="warning"/><span>{error}</span></div>}
  {!module.enabled?<DisabledSetup module={module} busy={busy} t={t} onEnable={()=>action(async()=>{await api('/baby/module/',{method:'PATCH',body:JSON.stringify({family:family.id,enabled:true})});await refresh()})}/>:!module.authorized?<Panel><div className="baby-locked"><Icon name="lock" size={28}/><strong>{t('babyUi.noAccess')}</strong><span>{t('babyUi.privacy')}</span></div></Panel>:<>
   <div className="baby-tabs" role="tablist">{canPregnancy&&<TabButton active={tab==='pregnancy'} onClick={()=>setTab('pregnancy')}>{t('babyUi.pregnancy')}</TabButton>}{baby&&canCare&&<TabButton active={tab==='now'} onClick={()=>setTab('now')}>{t('babyUi.now')}</TabButton>}{baby&&canGrowth&&<TabButton active={tab==='growth'} onClick={()=>setTab('growth')}>{t('babyUi.growth')}</TabButton>}{baby&&canGrowth&&<TabButton active={tab==='development'} onClick={()=>setTab('development')}>{t('babyUi.development')}</TabButton>}{baby&&(canCare||canGrowth)&&<TabButton active={tab==='report'} onClick={()=>setTab('report')}>{t('babyUi.report')}</TabButton>}{module.can_manage&&<TabButton active={tab==='settings'} onClick={()=>setTab('settings')}>{t('babyUi.settings')}</TabButton>}</div>
   {babies.length>1&&<label className="baby-selector"><span>{t('babyUi.babies')}</span><select value={baby?.id||''} onChange={e=>setSelectedBaby(e.target.value)}>{babies.map(row=><option value={row.id} key={row.id}>{row.display_name}</option>)}</select></label>}
   {tab==='pregnancy'&&canPregnancy&&<PregnancyPanel family={family} pregnancy={activePregnancy} t={t} busy={busy} action={action} refresh={refresh} canManage={!!module.can_manage} canManageChild={canManageChild}/>} 
   {tab==='now'&&baby&&canCare&&<BabyCarePanel baby={baby} t={t}/>} 
   {tab==='growth'&&baby&&canGrowth&&<GrowthPanel baby={baby} t={t} busy={busy} action={action}/>} 
   {tab==='development'&&baby&&canGrowth&&<DevelopmentPanel family={family} baby={baby} t={t} language={i18n.language.startsWith('en')?'en':'de'} busy={busy} action={action}/>} 
   {tab==='report'&&baby&&<BabyReportPanel baby={baby} t={t} canCare={canCare} canGrowth={canGrowth}/>} 
   {tab==='settings'&&module.can_manage&&<SettingsPanel family={family} module={module} t={t} busy={busy} action={action} refresh={refresh}/>} 
   {!baby&&tab!=='pregnancy'&&tab!=='settings'&&<Panel><div className="smart-empty"><Icon name="heart"/><strong>{t('babyUi.emptyBaby')}</strong></div></Panel>}
  </>}
 </div>;
}

function DisabledSetup({module,busy,t,onEnable}){
 return <Panel><div className="baby-locked"><Icon name="heart" size={30}/><h2>{t('babyUi.disabled')}</h2><p>{t('babyUi.activateHint')}</p>{module.can_manage?<button className="primary" disabled={busy} onClick={onEnable}><Icon name="plus"/>{t('babyUi.enable')}</button>:<span>{t('babyUi.noAccess')}</span>}</div></Panel>;
}

function PregnancyPanel({family,pregnancy,t,busy,action,refresh,canManage,canManageChild}){
 const [due,setDue]=useState('');
 const [count,setCount]=useState(1);
 const [journal,setJournal]=useState('');
 const [journalMedia,setJournalMedia]=useState(null);
 const [preferences,setPreferences]=useState('');
 const [eventTitle,setEventTitle]=useState('');
 const [eventAt,setEventAt]=useState('');
 const [contraction,setContraction]=useState(null);
 const [showBirth,setShowBirth]=useState(false);
 const [birth,setBirth]=useState({});
 const [born,setBorn]=useState({name:'',birth_date:dateToday(),gestational_age_weeks:'',birth_weight_g:'',growth_reference_sex:'unspecified'});
 useEffect(()=>{
  if(!pregnancy)return;
  setDue(pregnancy.expected_due_date);
  setBirth(Object.fromEntries((pregnancy.babies||[]).map(row=>[row.id,{pregnancy_baby:row.id,display_name:row.display_name||row.stable_label,birth_date:dateToday(),gestational_age_weeks:null,gestational_age_days:0,birth_weight_g:null,birth_length_cm:null,birth_head_circumference_cm:null,growth_reference_sex:'unspecified'}])));
  api(`/baby/pregnancies/${pregnancy.id}/birth-preferences/`).then(data=>setPreferences(data.birth_preferences||'')).catch(()=>{});
 },[pregnancy?.id]);
 if(!pregnancy){
  if(!canManage&&!canManageChild)return <Panel><div className="smart-empty"><Icon name="heart"/><strong>{t('babyUi.emptyPregnancy')}</strong></div></Panel>;
  return <>
   {canManage&&<Panel><h2>{t('babyUi.pregnancy')}</h2><div className="form-grid"><label>{t('babyUi.dueDate')}<input type="date" value={due} onChange={e=>setDue(e.target.value)}/></label><label>{t('babyUi.babyCount')}<select value={count} onChange={e=>setCount(Number(e.target.value))}><option value="1">1</option><option value="2">2</option><option value="3">3</option></select></label></div><button className="primary" disabled={busy||!due} onClick={()=>action(async()=>{await api('/baby/pregnancies/',{method:'POST',body:JSON.stringify({family:family.id,expected_due_date:due,baby_count:count})});await refresh()},t('babyUi.created'))}><Icon name="plus"/>{t('babyUi.startPregnancy')}</button></Panel>}
   {canManageChild&&<AlreadyBorn family={family} value={born} setValue={setBorn} t={t} busy={busy} action={action} refresh={refresh}/>} 
  </>;
 }
 async function archive(){
  const ok=await confirmAction({title:t('babyUi.archivePregnancy'),message:t('babyUi.archivePregnancyConfirm'),confirmLabel:t('babyUi.archivePregnancy'),danger:true});
  if(!ok)return;
  await action(async()=>{await api(`/baby/pregnancies/${pregnancy.id}/`,{method:'PATCH',body:JSON.stringify({status:'archived'})});await refresh()});
 }
 return <>
  <Panel className="pregnancy-hero"><small>{t('babyUi.dueDate')} · {pregnancy.expected_due_date}</small><h2>{t('babyUi.week',{week:pregnancy.progress.week,day:pregnancy.progress.day})}</h2><p>{t('babyUi.daysUntil',{count:pregnancy.progress.days_until_due})}</p><div className="baby-chip-row">{pregnancy.babies.map(row=><span className="chip" key={row.id}>{row.display_name||row.stable_label}</span>)}</div>{canManage&&<div className="baby-inline-form"><input aria-label={t('babyUi.dueDate')} type="date" value={due} onChange={e=>setDue(e.target.value)}/><button className="secondary compact" disabled={busy||!due||due===pregnancy.expected_due_date} onClick={()=>action(async()=>{await api(`/baby/pregnancies/${pregnancy.id}/`,{method:'PATCH',body:JSON.stringify({expected_due_date:due})});await refresh()})}>{t('babyUi.save')}</button></div>}<div className="baby-actions"><button className="secondary" disabled={busy} onClick={()=>action(()=>api(`/baby/pregnancies/${pregnancy.id}/templates/`,{method:'POST',body:JSON.stringify({tasks:true,shopping:true})}),t('babyUi.created'))}><Icon name="tasks"/>{t('babyUi.templates')}</button>{canManageChild&&<button className="primary" onClick={()=>setShowBirth(value=>!value)}><Icon name="heart"/>{t('babyUi.birth')}</button>}{canManage&&<button className="ghost-danger" disabled={busy} onClick={archive}>{t('babyUi.archivePregnancy')}</button>}</div></Panel>
  <Panel><h3>{t('babyUi.pregnancy')}</h3><div className="baby-quick-grid"><button disabled={busy} onClick={()=>action(()=>api(`/baby/pregnancies/${pregnancy.id}/utilities/`,{method:'POST',body:JSON.stringify({kind:'kick',started_at:isoNow(),ended_at:isoNow(),client_event_id:uid(),value:{count:1}})}))}><Icon name="plus"/><strong>{t('babyUi.kick')}</strong></button><button disabled={busy} onClick={()=>action(async()=>{if(!contraction){const row=await api(`/baby/pregnancies/${pregnancy.id}/utilities/`,{method:'POST',body:JSON.stringify({kind:'contraction',started_at:isoNow(),client_event_id:uid()})});setContraction(row)}else{await api(`/baby/pregnancy-utilities/${contraction.id}/`,{method:'PATCH',body:JSON.stringify({ended_at:isoNow()})});setContraction(null)}})}><Icon name="clock"/><strong>{contraction?t('babyUi.contractionStop'):t('babyUi.contractionStart')}</strong></button></div><label>{t('babyUi.journal')}<textarea value={journal} onChange={e=>setJournal(e.target.value)} placeholder={t('babyUi.journalPlaceholder')}/></label><BabyPrivateMediaField familyId={family.id} scope="pregnancy" pregnancyId={pregnancy.id} media={journalMedia} onChange={setJournalMedia} accept="image/jpeg,image/png,image/webp" capture="environment" title={t('babyUi.addPhoto')} hint={t('babyUi.mediaHint')} disabled={busy} savedLabel={t('babyUi.mediaSelected')} removeLabel={t('babyUi.removeMedia')} errorLabel={t('babyUi.error')}/><button className="secondary" disabled={busy||(!journal.trim()&&!journalMedia)} onClick={()=>action(async()=>{await api(`/baby/pregnancies/${pregnancy.id}/journal/`,{method:'POST',body:JSON.stringify({entry_date:dateToday(),note:journal,media_key:journalMedia?.id||''})});setJournal('');setJournalMedia(null)})}>{t('babyUi.save')}</button></Panel>
  <Panel><h3>{t('babyUi.birthPreferences')}</h3><p className="baby-reference-note">{t('babyUi.birthPreferencesHint')}</p><textarea value={preferences} onChange={e=>setPreferences(e.target.value)}/><button className="secondary" disabled={busy} onClick={()=>action(()=>api(`/baby/pregnancies/${pregnancy.id}/birth-preferences/`,{method:'PUT',body:JSON.stringify({birth_preferences:preferences})}))}>{t('babyUi.save')}</button></Panel>
  <Panel><h3>{t('babyUi.prenatalEvent')}</h3><div className="form-grid"><label>{t('babyUi.eventTitle')}<input value={eventTitle} onChange={e=>setEventTitle(e.target.value)}/></label><label>{t('babyUi.eventDate')}<input type="datetime-local" value={eventAt} onChange={e=>setEventAt(e.target.value)}/></label></div><button className="secondary" disabled={busy||!eventTitle||!eventAt} onClick={()=>action(async()=>{await api(`/baby/pregnancies/${pregnancy.id}/prenatal-event/`,{method:'POST',body:JSON.stringify({title:eventTitle,starts_at:new Date(eventAt).toISOString()})});setEventTitle('');setEventAt('')},t('babyUi.created'))}><Icon name="calendar"/>{t('babyUi.addToCalendar')}</button></Panel>
  {showBirth&&canManageChild&&<Panel><h2>{t('babyUi.birth')}</h2><div className="stack">{pregnancy.babies.map(expected=>{const row=birth[expected.id]||{};const set=(key,value)=>setBirth(current=>({...current,[expected.id]:{...current[expected.id],[key]:value}}));return <fieldset className="baby-birth-card" key={expected.id}><legend>{expected.display_name||expected.stable_label}</legend><div className="form-grid"><label>{t('babyUi.name')}<input value={row.display_name||''} onChange={e=>set('display_name',e.target.value)}/></label><label>{t('babyUi.birthDate')}<input type="date" value={row.birth_date||''} onChange={e=>set('birth_date',e.target.value)}/></label><label>{t('babyUi.gestation')}<input type="number" min="20" max="44" value={row.gestational_age_weeks??''} onChange={e=>set('gestational_age_weeks',e.target.value?Number(e.target.value):null)}/></label><label>{t('babyUi.birthWeight')}<input inputMode="numeric" value={row.birth_weight_g??''} onChange={e=>set('birth_weight_g',e.target.value?Number(e.target.value):null)}/></label><label>{t('babyUi.birthLength')}<input inputMode="decimal" value={row.birth_length_cm??''} onChange={e=>set('birth_length_cm',e.target.value?Number(e.target.value):null)}/></label><label>{t('babyUi.head')}<input inputMode="decimal" value={row.birth_head_circumference_cm??''} onChange={e=>set('birth_head_circumference_cm',e.target.value?Number(e.target.value):null)}/></label><label>{t('babyUi.growthSex')}<select value={row.growth_reference_sex||'unspecified'} onChange={e=>set('growth_reference_sex',e.target.value)}><option value="unspecified">{t('babyUi.unspecified')}</option><option value="female">{t('babyUi.female')}</option><option value="male">{t('babyUi.male')}</option></select></label></div></fieldset>})}</div><button className="primary" disabled={busy} onClick={()=>action(async()=>{await api(`/baby/pregnancies/${pregnancy.id}/birth/`,{method:'POST',body:JSON.stringify({babies:Object.values(birth).map(row=>({...row,gestational_age_weeks:row.gestational_age_weeks??null,birth_weight_g:row.birth_weight_g??null,birth_length_cm:row.birth_length_cm??null,birth_head_circumference_cm:row.birth_head_circumference_cm??null}))})});setShowBirth(false);await refresh()})}>{t('babyUi.saveBirth')}</button></Panel>}
 </>;
}

function AlreadyBorn({family,value,setValue,t,busy,action,refresh}){
 const set=(key,next)=>setValue(current=>({...current,[key]:next}));
 return <Panel><h3>{t('babyUi.alreadyBorn')}</h3><div className="form-grid"><label>{t('babyUi.name')}<input value={value.name} onChange={e=>set('name',e.target.value)}/></label><label>{t('babyUi.birthDate')}<input type="date" value={value.birth_date} onChange={e=>set('birth_date',e.target.value)}/></label><label>{t('babyUi.gestation')}<input type="number" min="20" max="44" value={value.gestational_age_weeks} onChange={e=>set('gestational_age_weeks',e.target.value)}/></label><label>{t('babyUi.birthWeight')}<input inputMode="numeric" value={value.birth_weight_g} onChange={e=>set('birth_weight_g',e.target.value)}/></label></div><button className="secondary" disabled={busy||!value.name||!value.birth_date} onClick={()=>action(async()=>{await api('/baby/profiles/',{method:'POST',body:JSON.stringify({family:family.id,client_identity_key:uid(),display_name:value.name,birth_date:value.birth_date,gestational_age_weeks:value.gestational_age_weeks?Number(value.gestational_age_weeks):null,birth_weight_g:value.birth_weight_g?Number(value.birth_weight_g):null,growth_reference_sex:value.growth_reference_sex})});await refresh()},t('babyUi.created'))}>{t('babyUi.save')}</button></Panel>;
}

function GrowthPanel({baby,t,busy,action}){
 const [data,setData]=useState(null);
 const [form,setForm]=useState({weight_g:'',length_cm:'',head_circumference_cm:'',source:'home'});
 async function load(){setData(await api(`/baby/profiles/${baby.id}/growth/`))}
 useEffect(()=>{load().catch(()=>{})},[baby.id]);
 const set=(key,value)=>setForm(current=>({...current,[key]:value}));
 return <><Panel><h2>{t('babyUi.growth')}</h2><div className="form-grid"><label>{t('babyUi.weight')}<input inputMode="numeric" value={form.weight_g} onChange={e=>set('weight_g',e.target.value)}/></label><label>{t('babyUi.length')}<input inputMode="decimal" value={form.length_cm} onChange={e=>set('length_cm',e.target.value)}/></label><label>{t('babyUi.head')}<input inputMode="decimal" value={form.head_circumference_cm} onChange={e=>set('head_circumference_cm',e.target.value)}/></label><label>{t('babyUi.source')}<select value={form.source} onChange={e=>set('source',e.target.value)}><option value="home">{t('babyUi.sourceHome')}</option><option value="midwife">{t('babyUi.sourceMidwife')}</option><option value="pediatrician">{t('babyUi.sourcePediatrician')}</option><option value="clinic">{t('babyUi.sourceClinic')}</option><option value="other">{t('babyUi.sourceOther')}</option></select></label></div><button className="primary" disabled={busy||(!form.weight_g&&!form.length_cm&&!form.head_circumference_cm)} onClick={()=>action(async()=>{await api(`/baby/profiles/${baby.id}/growth/`,{method:'POST',body:JSON.stringify({measured_at:isoNow(),weight_g:form.weight_g?Number(form.weight_g):null,length_cm:form.length_cm?Number(form.length_cm):null,head_circumference_cm:form.head_circumference_cm?Number(form.head_circumference_cm):null,source:form.source})});setForm({weight_g:'',length_cm:'',head_circumference_cm:'',source:'home'});await load()})}>{t('babyUi.record')}</button></Panel><Panel><label>{t('babyUi.reference')}<select value={data?.reference?.key||'who_2006'} onChange={e=>action(async()=>{await api(`/baby/profiles/${baby.id}/growth-reference/`,{method:'PATCH',body:JSON.stringify({reference_key:e.target.value,corrected_age_enabled:e.target.value==='who_2006_corrected'})});await load()})}><option value="who_2006">{t('babyUi.who')}</option><option value="who_2006_corrected">{t('babyUi.whoCorrected')}</option><option value="intergrowth_21_postnatal">{t('babyUi.intergrowth')}</option></select></label><p className="baby-reference-note">{data?.reference?.label&&`${data.reference.label} · ${data.reference.version}. `}{t('babyUi.percentileNote')}</p><GrowthChart points={data?.points||[]}/></Panel></>;
}
function GrowthChart({points}){
 const values=points.map(row=>row.metrics?.weight_g?.percentile).filter(value=>value!=null);
 if(!values.length)return <div className="smart-empty"><Icon name="trend"/><span>–</span></div>;
 const w=640,h=180;
 const path=values.map((value,index)=>`${index?'L':'M'} ${values.length===1?w/2:(index/(values.length-1))*w} ${h-(Math.max(0,Math.min(100,value))/100)*h}`).join(' ');
 return <svg className="baby-growth-chart" viewBox={`0 0 ${w} ${h}`} role="img" aria-label="Percentile trend"><line x1="0" x2={w} y1={h/2} y2={h/2}/><path d={path} fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round"/></svg>;
}

function DevelopmentPanel({family,baby,t,language,busy,action}){
 const [data,setData]=useState(null);
 const [title,setTitle]=useState('');
 const [note,setNote]=useState('');
 const [media,setMedia]=useState(null);
 async function load(){setData(await api(`/baby/profiles/${baby.id}/development/?language=${language}`))}
 useEffect(()=>{setTitle('');setNote('');setMedia(null);load().catch(()=>{})},[baby.id,language]);
 async function saveCustom(){await action(async()=>{await api(`/baby/profiles/${baby.id}/development/`,{method:'POST',body:JSON.stringify({title:title.trim(),state:'observed',observed_at:isoNow(),note,media_key:media?.id||''})});setTitle('');setNote('');setMedia(null);await load()},t('babyUi.created'))}
 return <Panel><div className="baby-section-head"><div><small>{data?.source?.key==='cdc_act_early'?'CDC':data?.source?.key||''}{data?.source?.version?` · ${data.source.version}`:''}</small><h2>{t('babyUi.development')} · {data?.checklist_age_months||'–'} M.</h2></div></div><p className="baby-reference-note">{data?.interpretation}</p>{data?.effective_age_days!=null&&data?.age_days!=null&&data.effective_age_days!==data.age_days&&<p className="baby-reference-note"><Icon name="info" size={14}/> {t('babyUi.correctedAgeActive')}</p>}<div className="baby-milestones">{(data?.items||[]).map(item=><article key={item.key}><small>{item.category}</small><strong>{item.text}</strong><div className="segmented">{[['observed',t('babyUi.observed')],['not_observed',t('babyUi.notObserved')],['later',t('babyUi.later')]].map(([state,label])=><button key={state} className={item.state===state?'active':''} disabled={busy} onClick={()=>action(async()=>{await api(`/baby/profiles/${baby.id}/development/`,{method:'POST',body:JSON.stringify({milestone_key:item.key,state})});await load()})}>{label}</button>)}</div></article>)}</div><BabyPreventivePanel baby={baby} t={t} language={language}/><div className="baby-custom-observation"><h3>{t('babyUi.customObservation')}</h3><div className="form-grid"><label>{t('babyUi.observationTitle')}<input value={title} onChange={e=>setTitle(e.target.value)} placeholder={t('babyUi.observationPlaceholder')}/></label><label>{t('babyUi.observationNote')}<textarea value={note} onChange={e=>setNote(e.target.value)} placeholder={t('babyUi.note')}/></label></div><BabyPrivateMediaField familyId={family.id} scope="development" babyId={baby.id} media={media} onChange={setMedia} accept="image/jpeg,image/png,image/webp,video/mp4,video/webm" title={t('babyUi.addMedia')} hint={t('babyUi.mediaHint')} disabled={busy} savedLabel={t('babyUi.mediaSelected')} removeLabel={t('babyUi.removeMedia')} errorLabel={t('babyUi.error')}/><button className="primary" disabled={busy||!title.trim()} onClick={saveCustom}>{t('babyUi.saveObservation')}</button></div>{(data?.custom_observations||[]).length>0&&<div className="baby-timeline"><h3>{t('babyUi.privateTimeline')}</h3>{data.custom_observations.map(row=><div className="baby-event" key={row.id}><Icon name="heart"/><div><strong>{row.title}</strong>{row.note&&<span>{row.note}</span>}<small>{row.observed_at?new Date(row.observed_at).toLocaleString():''}</small>{row.media_url&&<a className="text-button" href={row.media_url} target="_blank" rel="noreferrer">{t('babyUi.openMedia')}</a>}</div></div>)}</div>}</Panel>;
}

function SettingsPanel({family,module,t,busy,action,refresh}){
 const [rows,setRows]=useState([]);
 async function load(){const data=await api(`/baby/care-circle/?family=${family.id}`);setRows(data.care_circle||[])}
 useEffect(()=>{load().catch(()=>{})},[family.id]);
 const update=(id,key,value)=>setRows(current=>current.map(row=>row.membership===id?{...row,[key]:value}:row));
 const members=family.memberships||[];
 const merged=useMemo(()=>members.map(member=>{const existing=rows.find(row=>String(row.membership)===String(member.id));return existing||{membership:member.id,display_name:member.display_name,role:member.role,can_view_pregnancy:false,can_log_care:false,can_view_growth_development:false,is_guardian:false}}),[members,rows]);
 async function deleteData(){const ok=await confirmAction({title:t('babyUi.title'),message:'Tracking-Daten dauerhaft löschen? Child-Identitäten bleiben bestehen.',confirmLabel:'Dauerhaft löschen',danger:true});if(!ok)return;await action(async()=>{await api('/baby/module/',{method:'DELETE',body:JSON.stringify({family:family.id,confirm:'DELETE'})});await refresh()})}
 return <><Panel><Toggle checked={module.show_in_main_navigation} label={t('babyUi.showNav')} hint={t('babyUi.mainNavHint')} onChange={value=>action(async()=>{await api('/baby/module/',{method:'PATCH',body:JSON.stringify({family:family.id,show_in_main_navigation:value})});await refresh()})}/><button className="ghost-danger" disabled={busy} onClick={()=>action(async()=>{await api('/baby/module/',{method:'PATCH',body:JSON.stringify({family:family.id,enabled:false})});await refresh()})}>{t('babyUi.disable')}</button><button className="ghost-danger" disabled={busy} onClick={deleteData}>Tracking-Daten dauerhaft löschen</button></Panel><Panel><h2>{t('babyUi.careCircle')}</h2><div className="baby-care-circle">{merged.map(row=>{const guardianAllowed=['owner','adult'].includes(row.role);return <article key={row.membership}><div><strong>{row.display_name||row.role}</strong><small>{row.role}</small></div><Toggle checked={row.can_view_pregnancy} label={t('babyUi.pregnancyPermission')} onChange={value=>update(row.membership,'can_view_pregnancy',value)}/><Toggle checked={row.can_log_care} label={t('babyUi.carePermission')} onChange={value=>update(row.membership,'can_log_care',value)}/><Toggle checked={row.can_view_growth_development} label={t('babyUi.growthPermission')} onChange={value=>update(row.membership,'can_view_growth_development',value)}/><Toggle checked={guardianAllowed&&row.is_guardian} disabled={!guardianAllowed} label={t('babyUi.guardian')} onChange={value=>update(row.membership,'is_guardian',value)}/></article>})}</div><button className="primary" disabled={busy} onClick={()=>action(async()=>{await api('/baby/care-circle/',{method:'PUT',body:JSON.stringify({family:family.id,care_circle:merged.map(({membership,role,can_view_pregnancy,can_log_care,can_view_growth_development,is_guardian})=>({membership,can_view_pregnancy,can_log_care,can_view_growth_development,is_guardian:['owner','adult'].includes(role)&&is_guardian}))})});await load();await refresh()})}>{t('babyUi.save')}</button></Panel></>;
}
