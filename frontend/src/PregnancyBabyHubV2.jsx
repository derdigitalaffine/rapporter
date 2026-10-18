import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {confirmAction,toast} from './feedback';
import BabyPrivateMediaField from './BabyPrivateMediaField';
import BabyCarePanel from './BabyCarePanel';
import BabyReportPanel from './BabyReportPanel';
import ChildHealthPanel from './ChildHealthPanel';
import ChildCareCircle from './ChildCareCircle';
import PregnancyCareCircle from './PregnancyCareCircle';
import MemberAvatar from './MemberAvatar';
import {childAgeMonths,childPermissions,defaultChildView} from './children-context';
import {featureHref,updateFeatureLocation} from './navigation';
import './baby-i18n';
import './pregnancy-baby-hotfix-i18n';
import './pregnancy-baby.css';
import './pregnancy-baby-hotfix.css';
import './children-i18n';
import './children-hub.css';

const isoNow=()=>new Date().toISOString();
const dateToday=()=>new Date().toISOString().slice(0,10);
const uid=()=>crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`;

function Panel({children,className=''}){
 return <section className={`baby-panel ${className}`}>{children}</section>;
}

function Toggle({checked,onChange,label,hint,disabled=false}){
 return <label className="baby-toggle"><input type="checkbox" checked={checked} disabled={disabled} onChange={e=>onChange(e.target.checked)}/><span><strong>{label}</strong>{hint&&<small>{hint}</small>}</span></label>;
}

function PrimaryNav({items,active,onChange,label}){
 return <nav className="baby-primary-nav" aria-label={label}>{items.map(item=><button key={item.key} type="button" className={active===item.key?'active':''} aria-current={active===item.key?'page':undefined} onClick={()=>onChange(item.key)}>{item.label}</button>)}</nav>;
}

export default function PregnancyBabyHub({family,onBack,onModuleChange,onCreate}){
 const {t,i18n}=useTranslation();
 const [module,setModule]=useState(null);
 const [pregnancies,setPregnancies]=useState([]);
 const [babies,setBabies]=useState([]);
 const [selectedBaby,setSelectedBaby]=useState('');
 const [section,setSection]=useState('pregnancy');
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const requestRevision=useRef(0),initialized=useRef(false);
 const c=key=>t(`childrenUi.${key}`);
 const activePregnancy=pregnancies.find(row=>row.status==='active');
 const baby=babies.find(row=>String(row.id)===String(selectedBaby));
 const permissions=childPermissions(baby,module);
 const canPregnancy=!!module?.permissions?.can_view_pregnancy;
 const canCare=!!permissions.can_log_care;
 const canGrowth=!!permissions.can_view_growth_development;
 const canManageChild=!!(permissions.can_manage_account??permissions.is_guardian);

 async function refresh(){
  if(!family)return;
  const revision=++requestRevision.current;
  setError('');
  try{
   const row=await api(`/baby/module/?family=${encodeURIComponent(family.id)}`);
   const visible=row.enabled&&row.authorized;
   const [pregnancyData,childData]=await Promise.all([
    visible&&row.permissions?.can_view_pregnancy?api(`/baby/pregnancies/?family=${encodeURIComponent(family.id)}`):Promise.resolve({pregnancies:[]}),
    visible?api(`/baby/profiles/?family=${encodeURIComponent(family.id)}`):Promise.resolve({babies:[]}),
   ]);
   if(revision!==requestRevision.current)return;
   const next=childData.babies||[],params=new URLSearchParams(location.search);
   let requested=params.get('baby');
   if(params.get('event')){const target=await api(`/baby/health-events/${encodeURIComponent(params.get('event'))}/`);if(revision!==requestRevision.current)return;if(String(target.family)!==String(family.id))throw new Error(c('noChildContext'));requested=target.baby}
   setModule(row);onModuleChange?.(row);setPregnancies(pregnancyData.pregnancies||[]);setBabies(next);
   setSelectedBaby(previous=>requested||(next.some(item=>String(item.id)===String(previous))?previous:next[0]?.id||''));
   if(!initialized.current){
    initialized.current=true;
    const context=next.find(item=>String(item.id)===String(requested))||(!requested?next[0]:null);
    const view=params.get('view');
    setSection(['growth','development'].includes(view)?'longterm':['now','health','more','longterm','pregnancy'].includes(view)?view:(pregnancyData.pregnancies||[]).some(item=>item.status==='active')?'pregnancy':context?defaultChildView(context,row):row.permissions?.can_view_pregnancy?'pregnancy':'more');
   }
   if(requested&&!next.some(item=>String(item.id)===String(requested)))setError(c('noChildContext'));
  }catch(err){if(revision===requestRevision.current)setError(err.message||t('babyUi.error'))}
 }
 useEffect(()=>{initialized.current=false;setModule(null);setBabies([]);setPregnancies([]);setSelectedBaby('');refresh();return()=>{requestRevision.current++}},[family?.id]);
 useEffect(()=>{const changed=event=>{if(String(event.detail?.family)===String(family?.id))refresh()};window.addEventListener('familyos:children-changed',changed);return()=>window.removeEventListener('familyos:children-changed',changed)},[family?.id]);
 useEffect(()=>{const pop=()=>{const params=new URLSearchParams(location.search);if(params.get('baby'))setSelectedBaby(params.get('baby'));if(params.get('view'))setSection(['growth','development'].includes(params.get('view'))?'longterm':params.get('view'))};window.addEventListener('popstate',pop);return()=>window.removeEventListener('popstate',pop)},[]);
 function selectSection(next){if(updateFeatureLocation('baby',{view:next,baby:next==='pregnancy'?null:baby?.id,event:null}))setSection(next)}
 function selectChild(id){const context=babies.find(row=>String(row.id)===String(id));if(!context)return;const next=defaultChildView(context,module);if(updateFeatureLocation('baby',{baby:id,view:next,event:null})){setSelectedBaby(id);setSection(next)}}
 async function action(fn,success=t('babyUi.saved')){
  setBusy(true);setError('');
  try{const result=await fn();toast(success,{type:'success'});return result}
  catch(err){setError(err.message||t('babyUi.error'));toast(err.message||t('babyUi.error'),{type:'error'});throw err}
  finally{setBusy(false)}
 }

 const primaryItems=useMemo(()=>{
  const items=[];
  if(canPregnancy)items.push({key:'pregnancy',label:t('babyUi.pregnancy')});
  if(baby&&canCare&&(childAgeMonths(baby)<24||section==='now'))items.push({key:'now',label:t('babyUi.now')});
  if(baby&&canGrowth)items.push({key:'health',label:c('health')});
  if(baby&&canGrowth)items.push({key:'longterm',label:t('babyUi.growthDevelopment')});
  if((baby&&(canCare||canGrowth))||module?.can_manage)items.push({key:'more',label:t('babyUi.more')});
  return items;
 },[canPregnancy,canCare,canGrowth,baby?.id,module?.can_manage,t,section]);

 useEffect(()=>{
  if(!primaryItems.length)return;
  if(primaryItems.some(item=>item.key===section))return;
  const preferred=primaryItems.find(item=>item.key===(activePregnancy&&canPregnancy?'pregnancy':baby?defaultChildView(baby,module):'more'))||primaryItems[0];
  setSection(preferred.key);
 },[primaryItems.map(item=>item.key).join('|'),baby?.id,activePregnancy?.id]);

 if(!family)return null;
 if(!module)return error?<div className="integration-notice" role="alert"><span>{error}</span><button type="button" className="secondary" onClick={refresh}>{c('reload')}</button></div>:<div className="smart-empty" role="status"><Icon name="refresh"/><strong>{t('babyUi.loading')}</strong></div>;
 return <div className="baby-page">
  <div className="page-head"><button className="back-button" onClick={onBack} aria-label={t('back')}><Icon name="back"/></button><div className="grow"><small>{c('private')}</small><h1>{c('title')}</h1></div><span className="baby-private-pill"><Icon name="lock" size={13}/>{t('babyUi.careCircle')}</span></div>
  {error&&<div className="integration-notice" role="alert"><Icon name="warning"/><span>{error}</span></div>}
  {!module.enabled?<DisabledSetup module={module} busy={busy} t={t} onEnable={()=>action(async()=>{await api('/baby/module/',{method:'PATCH',body:JSON.stringify({family:family.id,enabled:true})});await refresh()})}/>:!module.authorized?<Panel><div className="baby-locked"><Icon name="lock" size={28}/><strong>{t('babyUi.noAccess')}</strong><span>{t('babyUi.privacy')}</span></div></Panel>:<>
   {babies.length>0&&<div className="child-context-bar"><MemberAvatar person={{...family.memberships?.find(row=>String(row.id)===String(baby?.membership)),display_name:baby?.display_name}} decorative/><label className="baby-selector"><span>{c('select')}</span><select value={baby?.id||''} onChange={event=>selectChild(event.target.value)}>{!baby&&<option value="">{c('select')}</option>}{babies.map(row=><option value={row.id} key={row.id}>{row.display_name}</option>)}</select></label>{baby&&<span className="child-access-label"><Icon name={permissions.source==='custody'?'lock':'members'} size={16}/>{permissions.source==='custody'?c('custody'):permissions.is_guardian?c('legacy'):c('delegated')}</span>}</div>}
   <PrimaryNav items={primaryItems} active={section} onChange={selectSection} label={c('title')}/>
   {baby&&section!=='pregnancy'&&<div className="child-current-context" aria-live="polite"><span>{c('child')}: <strong>{baby.display_name}</strong> · {childAgeMonths(baby)<24?`${childAgeMonths(baby)} ${c('months')}`:`${Math.floor(childAgeMonths(baby)/12)} ${c('years')}`}</span>{onCreate&&canCare&&childAgeMonths(baby)<24&&<button type="button" className="primary" onClick={()=>onCreate('baby',{babyId:baby.id})}><Icon name="plus"/>{t('babyUi.add')}</button>}</div>}
   {section==='pregnancy'&&canPregnancy&&<PregnancyPanel family={family} pregnancy={activePregnancy} t={t} busy={busy} action={action} refresh={refresh} canManage={!!module.can_manage} canManageChild={!!module.can_manage}/>}
   {section==='now'&&baby&&canCare&&<BabyCarePanel key={baby.id} baby={baby} t={t}/>}
   {section==='health'&&baby&&canGrowth&&<ChildHealthPanel key={baby.id} baby={baby}/>}
   {section==='longterm'&&baby&&canGrowth&&<div className="baby-combined-section" key={baby.id}><div><h2 className="baby-lifecycle-heading">{baby.display_name} · {t('babyUi.growthDevelopment')}</h2><p className="baby-section-intro">{t('babyUi.percentileNote')}</p></div><GrowthPanel baby={baby} t={t} busy={busy} action={action}/><DevelopmentPanel family={family} baby={baby} t={t} language={i18n.language.startsWith('en')?'en':'de'} busy={busy} action={action}/></div>}
   {section==='more'&&<><div className="child-secondary-links"><a href={featureHref('members')}><Icon name="members"/>{c('members')}</a>{baby&&canCare&&childAgeMonths(baby)>=24&&<button type="button" onClick={()=>selectSection('now')}><Icon name="history"/>{c('careHistory')}</button>}</div>{baby&&canManageChild&&<ChildCareCircle key={baby.id} baby={baby} family={family}/>}<MorePanel family={family} module={module} baby={baby} babies={babies.filter(row=>row.permissions?.can_manage_account??canManageChild)} t={t} busy={busy} action={action} refresh={refresh} canCare={canCare} canGrowth={canGrowth} canManageChild={canManageChild}/></>}
   {!babies.length&&!activePregnancy&&<div className="child-empty"><p>{c('noChildren')}</p>{module.can_manage&&(onCreate&&module.authorized?<button type="button" className="secondary" onClick={()=>onCreate('baby',{intent:'child'})}><Icon name="plus"/>{c('addChild')}</button>:<a className="secondary" href={featureHref('members')}><Icon name="plus"/>{c('addChild')}</a>)}</div>}
   {!primaryItems.length&&<Panel><div className="baby-empty-context"><strong>{t('babyUi.noDailyView')}</strong></div></Panel>}
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
 const [addMode,setAddMode]=useState('journal');
 const [born,setBorn]=useState({name:'',birth_date:dateToday(),gestational_age_weeks:'',birth_weight_g:'',growth_reference_sex:'unspecified'});
 useEffect(()=>{
  if(!pregnancy)return;
  setDue(pregnancy.expected_due_date);
  setBirth(Object.fromEntries((pregnancy.babies||[]).map(row=>[row.id,{pregnancy_baby:row.id,display_name:row.display_name||row.stable_label,birth_date:dateToday(),gestational_age_weeks:null,gestational_age_days:0,birth_weight_g:null,birth_length_cm:null,birth_head_circumference_cm:null,growth_reference_sex:'unspecified'}])));
  api(`/baby/pregnancies/${pregnancy.id}/birth-preferences/`).then(data=>setPreferences(data.birth_preferences||'')).catch(()=>{});
  api(`/baby/pregnancies/${pregnancy.id}/utilities/`).then(data=>setContraction((data.sessions||[]).find(row=>row.kind==='contraction'&&!row.ended_at)||null)).catch(()=>{});
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
 async function toggleContraction(){
  await action(async()=>{
   if(!contraction){const row=await api(`/baby/pregnancies/${pregnancy.id}/utilities/`,{method:'POST',body:JSON.stringify({kind:'contraction',started_at:isoNow(),client_event_id:uid()})});setContraction(row)}
   else{await api(`/baby/pregnancy-utilities/${contraction.id}/`,{method:'PATCH',body:JSON.stringify({ended_at:isoNow()})});setContraction(null)}
  });
 }
 return <>
  <Panel className="pregnancy-hero"><small>{t('babyUi.dueDate')} · {pregnancy.expected_due_date}</small><h2>{t('babyUi.week',{week:pregnancy.progress.week,day:pregnancy.progress.day})}</h2><p>{t('babyUi.daysUntil',{count:pregnancy.progress.days_until_due})}</p><div className="baby-chip-row">{pregnancy.babies.map(row=><span className="chip" key={row.id}>{row.display_name||row.stable_label}</span>)}</div>{canManage&&<div className="baby-inline-form"><input aria-label={t('babyUi.dueDate')} type="date" value={due} onChange={e=>setDue(e.target.value)}/><button className="secondary compact" disabled={busy||!due||due===pregnancy.expected_due_date} onClick={()=>action(async()=>{await api(`/baby/pregnancies/${pregnancy.id}/`,{method:'PATCH',body:JSON.stringify({expected_due_date:due})});await refresh()})}>{t('babyUi.save')}</button></div>}{canManageChild&&<div className="baby-actions"><button className="primary" onClick={()=>setShowBirth(value=>!value)}><Icon name="heart"/>{t('babyUi.birth')}</button></div>}</Panel>
  {contraction&&<Panel className="baby-active-timer"><Icon name="clock"/><div className="grow"><small>{t('babyUi.pregnancy')}</small><strong>{t('babyUi.contractionStart')} · {new Date(contraction.started_at).toLocaleTimeString()}</strong></div><button className="primary compact" disabled={busy} onClick={toggleContraction}>{t('babyUi.contractionStop')}</button></Panel>}
  <Panel className="baby-add-card"><h2>{t('babyUi.add')}</h2><div className="baby-add-choices" role="group" aria-label={t('babyUi.add')}>{[['journal',t('babyUi.addJournal')],['event',t('babyUi.addAppointment')],['prepare',t('babyUi.addPreparation')]].map(([key,label])=><button type="button" className={addMode===key?'secondary active':'secondary'} key={key} onClick={()=>setAddMode(key)}>{label}</button>)}</div>{addMode==='journal'&&<><label>{t('babyUi.journal')}<textarea value={journal} onChange={e=>setJournal(e.target.value)} placeholder={t('babyUi.journalPlaceholder')}/></label><BabyPrivateMediaField familyId={family.id} scope="pregnancy" pregnancyId={pregnancy.id} media={journalMedia} onChange={setJournalMedia} accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif" capture="environment" title={t('babyUi.addPhoto')} hint={t('babyUi.mediaHint')} disabled={busy} savedLabel={t('babyUi.mediaSelected')} removeLabel={t('babyUi.removeMedia')} errorLabel={t('babyUi.error')}/><button className="primary" disabled={busy||(!journal.trim()&&!journalMedia)} onClick={()=>action(async()=>{await api(`/baby/pregnancies/${pregnancy.id}/journal/`,{method:'POST',body:JSON.stringify({entry_date:dateToday(),note:journal,media_key:journalMedia?.id||''})});setJournal('');setJournalMedia(null)})}>{t('babyUi.save')}</button></>}{addMode==='event'&&<><div className="form-grid"><label>{t('babyUi.eventTitle')}<input value={eventTitle} onChange={e=>setEventTitle(e.target.value)}/></label><label>{t('babyUi.eventDate')}<input type="datetime-local" value={eventAt} onChange={e=>setEventAt(e.target.value)}/></label></div><button className="primary" disabled={busy||!eventTitle||!eventAt} onClick={()=>action(async()=>{await api(`/baby/pregnancies/${pregnancy.id}/prenatal-event/`,{method:'POST',body:JSON.stringify({title:eventTitle,starts_at:new Date(eventAt).toISOString()})});setEventTitle('');setEventAt('')},t('babyUi.created'))}><Icon name="calendar"/>{t('babyUi.addToCalendar')}</button></>}{addMode==='prepare'&&<button className="primary" disabled={busy} onClick={()=>action(()=>api(`/baby/pregnancies/${pregnancy.id}/templates/`,{method:'POST',body:JSON.stringify({tasks:true,shopping:true})}),t('babyUi.preparationCreated'))}><Icon name="tasks"/>{t('babyUi.templates')}</button>}</Panel>
  {showBirth&&canManageChild&&<Panel><h2>{t('babyUi.birth')}</h2><div className="stack">{pregnancy.babies.map(expected=>{const row=birth[expected.id]||{};const set=(key,value)=>setBirth(current=>({...current,[expected.id]:{...current[expected.id],[key]:value}}));return <fieldset className="baby-birth-card" key={expected.id}><legend>{expected.display_name||expected.stable_label}</legend><div className="form-grid"><label>{t('babyUi.name')}<input value={row.display_name||''} onChange={e=>set('display_name',e.target.value)}/></label><label>{t('babyUi.birthDate')}<input type="date" value={row.birth_date||''} onChange={e=>set('birth_date',e.target.value)}/></label><label>{t('babyUi.gestation')}<input type="number" min="20" max="44" value={row.gestational_age_weeks??''} onChange={e=>set('gestational_age_weeks',e.target.value?Number(e.target.value):null)}/></label><label>{t('babyUi.birthWeight')}<input inputMode="numeric" value={row.birth_weight_g??''} onChange={e=>set('birth_weight_g',e.target.value?Number(e.target.value):null)}/></label><label>{t('babyUi.birthLength')}<input inputMode="decimal" value={row.birth_length_cm??''} onChange={e=>set('birth_length_cm',e.target.value?Number(e.target.value):null)}/></label><label>{t('babyUi.head')}<input inputMode="decimal" value={row.birth_head_circumference_cm??''} onChange={e=>set('birth_head_circumference_cm',e.target.value?Number(e.target.value):null)}/></label><label>{t('babyUi.growthSex')}<select value={row.growth_reference_sex||'unspecified'} onChange={e=>set('growth_reference_sex',e.target.value)}><option value="unspecified">{t('babyUi.unspecified')}</option><option value="female">{t('babyUi.female')}</option><option value="male">{t('babyUi.male')}</option></select></label></div></fieldset>})}</div><button className="primary" disabled={busy} onClick={()=>action(async()=>{await api(`/baby/pregnancies/${pregnancy.id}/birth/`,{method:'POST',body:JSON.stringify({babies:Object.values(birth).map(row=>({...row,gestational_age_weeks:row.gestational_age_weeks??null,birth_weight_g:row.birth_weight_g??null,birth_length_cm:row.birth_length_cm??null,birth_head_circumference_cm:row.birth_head_circumference_cm??null}))})});setShowBirth(false);await refresh()})}>{t('babyUi.saveBirth')}</button></Panel>}
  <details className="baby-more-details"><summary><Icon name="more"/>{t('babyUi.morePregnancy')}</summary><div className="baby-more-body"><Panel><h3>{t('babyUi.pregnancyTools')}</h3><div className="baby-quick-grid"><button disabled={busy} onClick={()=>action(()=>api(`/baby/pregnancies/${pregnancy.id}/utilities/`,{method:'POST',body:JSON.stringify({kind:'kick',started_at:isoNow(),ended_at:isoNow(),client_event_id:uid(),value:{count:1}})}))}><Icon name="plus"/><strong>{t('babyUi.kick')}</strong></button><button className={contraction?'active':''} disabled={busy} onClick={toggleContraction}><Icon name="clock"/><strong>{contraction?t('babyUi.contractionStop'):t('babyUi.contractionStart')}</strong></button></div></Panel><Panel><h3>{t('babyUi.birthPreferences')}</h3><p className="baby-reference-note">{t('babyUi.birthPreferencesHint')}</p><textarea value={preferences} onChange={e=>setPreferences(e.target.value)}/><button className="secondary" disabled={busy} onClick={()=>action(()=>api(`/baby/pregnancies/${pregnancy.id}/birth-preferences/`,{method:'PUT',body:JSON.stringify({birth_preferences:preferences})}))}>{t('babyUi.save')}</button></Panel>{canManage&&<Panel><button className="ghost-danger" disabled={busy} onClick={archive}>{t('babyUi.archivePregnancy')}</button></Panel>}</div></details>
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
 return <Panel><div className="baby-section-head"><div><small>{data?.source?.key==='cdc_act_early'?'CDC':data?.source?.key||''}{data?.source?.version?` · ${data.source.version}`:''}</small><h2>{t('babyUi.development')} · {childAgeMonths(baby)<=24?`${data?.checklist_age_months||'–'} M.`:''}</h2></div></div><p className="baby-reference-note">{t('childrenUi.observationNotice')}</p>{data?.effective_age_days!=null&&data?.age_days!=null&&data.effective_age_days!==data.age_days&&<p className="baby-reference-note"><Icon name="info" size={14}/> {t('babyUi.correctedAgeActive')}</p>}<div className="baby-milestones">{(childAgeMonths(baby)<=24?data?.items||[]:[]).map(item=><article key={item.key}><small>{item.category}</small><strong>{item.text}</strong><div className="segmented">{[['observed',t('babyUi.observed')],['not_observed',t('babyUi.notObserved')],['later',t('babyUi.later')]].map(([state,label])=><button key={state} className={item.state===state?'active':''} disabled={busy} onClick={()=>action(async()=>{await api(`/baby/profiles/${baby.id}/development/`,{method:'POST',body:JSON.stringify({milestone_key:item.key,state})});await load()})}>{label}</button>)}</div></article>)}</div><div className="baby-custom-observation"><h3>{t('babyUi.customObservation')}</h3><div className="form-grid"><label>{t('babyUi.observationTitle')}<input value={title} onChange={e=>setTitle(e.target.value)} placeholder={t('babyUi.observationPlaceholder')}/></label><label>{t('babyUi.observationNote')}<textarea value={note} onChange={e=>setNote(e.target.value)} placeholder={t('babyUi.note')}/></label></div><BabyPrivateMediaField familyId={family.id} scope="development" babyId={baby.id} media={media} onChange={setMedia} accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif,video/mp4,video/webm" title={t('babyUi.addMedia')} hint={t('babyUi.mediaHint')} disabled={busy} savedLabel={t('babyUi.mediaSelected')} removeLabel={t('babyUi.removeMedia')} errorLabel={t('babyUi.error')}/><button className="primary" disabled={busy||!title.trim()} onClick={saveCustom}>{t('babyUi.saveObservation')}</button></div>{(data?.custom_observations||[]).length>0&&<div className="baby-timeline"><h3>{t('babyUi.privateTimeline')}</h3>{data.custom_observations.map(row=><div className="baby-event" key={row.id}><Icon name="heart"/><div><strong>{row.title}</strong>{row.note&&<span>{row.note}</span>}<small>{row.observed_at?new Date(row.observed_at).toLocaleString():''}</small>{row.media_url&&<a className="text-button" href={row.media_url} target="_blank" rel="noreferrer">{t('babyUi.openMedia')}</a>}</div></div>)}</div>}</Panel>;
}

function MorePanel({family,module,baby,babies,t,busy,action,refresh,canCare,canGrowth,canManageChild}){
 return <div className="baby-more-stack">
  {baby&&(canCare||canGrowth)&&<><div className="baby-more-heading"><Icon name="report"/><h2>{t('babyUi.reportAndHandover')}</h2></div><BabyReportPanel baby={baby} t={t} canCare={canCare} canGrowth={canGrowth}/></>}
  {module.can_manage&&<><div className="baby-more-heading"><Icon name="settings"/><h2>{t('babyUi.settingsAndPrivacy')}</h2></div><SettingsPanel family={family} module={module} babies={babies} t={t} busy={busy} action={action} refresh={refresh} canManageChild={canManageChild}/></>}
 </div>;
}

function ChildManagement({babies,t,busy,action,refresh}){
 const [drafts,setDrafts]=useState({});
 useEffect(()=>setDrafts(Object.fromEntries(babies.map(row=>[row.id,row.display_name]))),[babies.map(row=>`${row.id}:${row.display_name}`).join('|')]);
 async function rename(row){
  const next=String(drafts[row.id]||'').trim();
  if(!next||next===row.display_name)return;
  const first=await confirmAction({title:t('babyUi.renameChild'),message:t('babyUi.renameConfirmFirst',{name:row.display_name}),confirmLabel:t('babyUi.renameChild')});
  if(!first)return;
  const second=await confirmAction({title:t('babyUi.renameChild'),message:t('babyUi.renameConfirmSecond',{name:row.display_name,next}),confirmLabel:t('babyUi.renameChild')});
  if(!second)return;
  await action(async()=>{await api(`/baby/profiles/${row.id}/`,{method:'PATCH',body:JSON.stringify({display_name:next})});await refresh()},t('babyUi.renameDone'));
 }
 async function remove(row){
  const first=await confirmAction({title:t('babyUi.deleteChild'),message:t('babyUi.deleteConfirmFirst',{name:row.display_name}),confirmLabel:t('babyUi.deleteChild'),danger:true});
  if(!first)return;
  const second=await confirmAction({title:t('babyUi.deleteChild'),message:t('babyUi.deleteConfirmSecond',{name:row.display_name}),confirmLabel:t('babyUi.deleteChild'),danger:true});
  if(!second)return;
  await action(async()=>{await api(`/baby/profiles/${row.id}/`,{method:'DELETE',body:JSON.stringify({confirm:'DELETE_CHILD',confirm_name:row.display_name})});await refresh()},t('babyUi.childRemoved'));
 }
 return <Panel><h2>{t('babyUi.childManagement')}</h2><p className="baby-reference-note">{t('babyUi.childManagementHint')}</p><div className="baby-child-management">{babies.map(row=><article className="baby-child-card" key={row.id}><header><strong>{row.display_name}</strong><small>{row.birth_date}</small></header><div className="baby-child-rename"><label>{t('babyUi.name')}<input value={drafts[row.id]??row.display_name} onChange={e=>setDrafts(current=>({...current,[row.id]:e.target.value}))}/></label><button className="secondary" disabled={busy||!String(drafts[row.id]||'').trim()||String(drafts[row.id]||'').trim()===row.display_name} onClick={()=>rename(row)}>{t('babyUi.renameChild')}</button></div><button className="ghost-danger" disabled={busy} onClick={()=>remove(row)}>{t('babyUi.deleteChild')}</button></article>)}</div></Panel>;
}

function SettingsPanel({family,module,babies,t,busy,action,refresh,canManageChild}){
 async function deleteData(){
  const first=await confirmAction({title:t('babyUi.trackingDelete'),message:t('babyUi.trackingDeleteFirst'),confirmLabel:t('babyUi.trackingDelete'),danger:true});
  if(!first)return;
  const second=await confirmAction({title:t('babyUi.trackingDelete'),message:t('babyUi.trackingDeleteSecond'),confirmLabel:t('babyUi.trackingDelete'),danger:true});
  if(!second)return;
  await action(async()=>{await api('/baby/module/',{method:'DELETE',body:JSON.stringify({family:family.id,confirm:'DELETE'})});await refresh()});
 }
 return <>
  {canManageChild&&babies.length>0&&<ChildManagement babies={babies} t={t} busy={busy} action={action} refresh={refresh}/>}
  <Panel><h2>{t('babyUi.privacySettings')}</h2><Toggle checked={module.show_in_main_navigation} disabled={busy} label={t('babyUi.showNav')} hint={t('babyUi.mainNavHint')} onChange={value=>action(async()=>{await api('/baby/module/',{method:'PATCH',body:JSON.stringify({family:family.id,show_in_main_navigation:value})});await refresh()})}/><button className="ghost-danger" disabled={busy} onClick={()=>action(async()=>{await api('/baby/module/',{method:'PATCH',body:JSON.stringify({family:family.id,enabled:false})});await refresh()})}>{t('babyUi.disable')}</button></Panel>
  <PregnancyCareCircle family={family}/>
  {module.can_delete_tracking&&<Panel className="baby-danger-zone"><h3>{t('babyUi.destructiveActions')}</h3><p className="baby-danger-copy">{t('babyUi.identitySafety')}</p><button className="ghost-danger" disabled={busy} onClick={deleteData}>{t('babyUi.trackingDelete')}</button></Panel>}
 </>;
}
