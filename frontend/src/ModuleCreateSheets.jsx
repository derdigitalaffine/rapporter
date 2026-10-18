import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {confirmAction,toast} from './feedback';
import BabyCarePanel from './BabyCarePanel';
import FamilySheet from './ui/FamilySheet';
import {childPermissions} from './children-context';
import ChildCreateForm from './ChildCreateForm';
import {EntityPicker} from './form-primitives';
import './baby-i18n';
import './pet-i18n';
import './pregnancy-baby.css';
import './pet.css';
import './module-create.css';

const PET_QUICK=new Set(['feed','water','walk','toilet','grooming','training']);
const now=()=>new Date().toISOString();
const uid=()=>crypto.randomUUID?.()||`${Date.now()}-${Math.random()}`;

function Sheet({family,title,onClose,onEscape=onClose,children,busy=false}){
  const {t}=useTranslation();
  const dialogRef=useRef(null);
  useEffect(()=>{
    const frame=requestAnimationFrame(()=>dialogRef.current?.focus({preventScroll:true}));
    return()=>cancelAnimationFrame(frame);
  },[]);
  useEffect(()=>{
    const keydown=event=>{if(event.key==='Escape'&&!busy){event.preventDefault();onEscape()}};
    window.addEventListener('keydown',keydown);
    return()=>window.removeEventListener('keydown',keydown);
  },[busy,onEscape]);
  return <div className="sheet-backdrop" onMouseDown={event=>{if(event.target===event.currentTarget&&!busy)onClose()}}>
    <section ref={dialogRef} className="quick-sheet module-create-sheet" role="dialog" aria-modal="true" aria-labelledby="module-create-title" tabIndex={-1}>
      <div className="sheet-handle"/>
      <div className="sheet-head"><div><small>{family?.name}</small><h2 id="module-create-title">{title}</h2></div><button type="button" className="sheet-close" onClick={onClose} disabled={busy} aria-label={t('createUi.close')}><Icon name="close"/></button></div>
      {children}
    </section>
  </div>;
}

function Loading({label}){return <div className="smart-empty" role="status"><Icon name="refresh"/><strong>{label}</strong></div>}
function ErrorNotice({message}){return message?<div className="integration-notice" role="alert"><Icon name="warning"/><span>{message}</span></div>:null}

function BabySheet({family,title,onClose,onEscape=onClose,children,busy=false}){
 const {t}=useTranslation();
 return <FamilySheet labelledBy="baby-create-title" onClose={onEscape} busy={busy}><div className="sheet-head"><div><small>{family?.name}</small><h2 id="baby-create-title">{title}</h2></div><button type="button" className="sheet-close" onClick={onClose} disabled={busy} aria-label={t('createUi.close')}><Icon name="close"/></button></div><div className="module-create-sheet">{children}</div></FamilySheet>;
}

export function BabyCreateSheet({family,context,onClose,onOpenPage,onSuccessfulCreate,onRefresh}){
  const {t}=useTranslation();
  const [moduleState,setModuleState]=useState(null);
  const [pregnancies,setPregnancies]=useState([]);
  const [babies,setBabies]=useState([]);
  const [selectedIds,setSelectedIds]=useState([]);
  const [view,setView]=useState('root');
  const [error,setError]=useState('');
  const [childBusy,setChildBusy]=useState(false),[childDirty,setChildDirty]=useState(false);
  const [attempt,setAttempt]=useState(0);
  useEffect(()=>{let live=true;(async()=>{
    setModuleState(null);setPregnancies([]);setBabies([]);setSelectedIds([]);setView(context?.intent==='child'?'child':'root');setError('');setChildDirty(false);
    try{
      const state=await api(`/baby/module/?family=${encodeURIComponent(family.id)}`);
      if(!live)return;setModuleState(state);
      if(!state?.enabled||!state?.authorized)return;
      const jobs=[];
      if(state.permissions?.can_view_pregnancy)jobs.push(api(`/baby/pregnancies/?family=${encodeURIComponent(family.id)}`).then(data=>{if(live)setPregnancies(data.pregnancies||[])}));
      if(state.permissions?.can_log_care||state.permissions?.can_view_growth_development)jobs.push(api(`/baby/profiles/?family=${encodeURIComponent(family.id)}`).then(data=>{if(!live)return;const rows=data.babies||[];setBabies(rows);const requested=rows.find(row=>String(row.id)===String(context?.babyId));if(requested)setSelectedIds([requested.id]);else if(rows.length===1)setSelectedIds([rows[0].id])}));
      await Promise.all(jobs);
    }catch(err){if(live)setError(err.message||t('babyUi.error'))}
  })();return()=>{live=false}},[family.id,t,attempt]);
  if(!moduleState)return <BabySheet family={family} title={t('createUi.baby')} onClose={onClose}>{error?<><ErrorNotice message={error}/><button type="button" className="secondary" onClick={()=>setAttempt(value=>value+1)}>{t('childrenUi.reload')}</button></>:<Loading label={t('babyUi.loading')}/>}</BabySheet>;
  const activePregnancy=pregnancies.find(row=>row.status==='active');
  const selectedBaby=babies.find(row=>String(row.id)===String(selectedIds[0]));
  const canCare=Boolean(childPermissions(selectedBaby,moduleState).can_log_care);
  const chooseRequired=babies.length>1&&!selectedBaby;
  async function close(){if(childBusy)return;if(childDirty&&!await confirmAction({title:t('childrenUi.close'),message:t('childrenUi.unsaved'),confirmLabel:t('childrenUi.discard'),cancelLabel:t('childrenUi.keep')}))return;onClose()}
  const escape=()=>view==='care'?setView('root'):close();
  return <BabySheet family={family} title={t('createUi.baby')} onClose={close} onEscape={escape} busy={childBusy}>
    <div className="module-create-body">
      <ErrorNotice message={error}/>
      {(!moduleState.enabled||!moduleState.authorized)&&<div className="smart-empty"><Icon name="lock"/><strong>{t('babyUi.noAccess')}</strong></div>}
      {moduleState.enabled&&moduleState.authorized&&view==='root'&&<>
        {babies.length>1&&<EntityPicker id="baby-create-context" label={t('babyUi.babies')} description={t('createUi.chooseBaby')} items={babies} selectedIds={selectedIds} onChange={ids=>setSelectedIds(ids.slice(-1))} multiple={false} getItemLabel={baby=>baby.display_name||baby.stable_label||String(baby.id)}/>} 
        <div className="module-create-actions">
          {moduleState.can_manage&&<button type="button" className="secondary" onClick={()=>setView('child')}><Icon name="plus"/>{t('childrenUi.addChild')}</button>}
          {canCare&&babies.length>0&&<button type="button" className="primary" disabled={chooseRequired} onClick={()=>setView('care')}><Icon name="heart"/><span><strong>{t('createUi.babyCare')}</strong><small>{chooseRequired?t('createUi.chooseBaby'):selectedBaby?.display_name}</small></span></button>}
          {activePregnancy&&moduleState.permissions?.can_view_pregnancy&&<button type="button" className="secondary" onClick={()=>onOpenPage('pregnancy')}><Icon name="heart"/><span><strong>{t('createUi.openPregnancy')}</strong><small>{activePregnancy.expected_due_date||''}</small></span></button>}
          <button type="button" className="secondary" onClick={()=>onOpenPage('baby')}><Icon name="next"/><span><strong>{t('createUi.openBaby')}</strong><small>{t('createUi.openModuleHint')}</small></span></button>
        </div>
      </>}
      {moduleState.enabled&&moduleState.authorized&&view==='care'&&selectedBaby&&<><button type="button" className="text-button module-create-back" onClick={()=>setView('root')}><Icon name="back"/>{t('createUi.back')}</button><BabyCarePanel baby={selectedBaby} t={t} onRecorded={onSuccessfulCreate}/></>}
      {moduleState.enabled&&moduleState.can_manage&&view==='child'&&<ChildCreateForm family={family} canRecordCustody={moduleState.can_record_custody_on_create} onBusyChange={setChildBusy} onDirtyChange={setChildDirty} onCancel={close} onSaved={async(child,{hasCustody})=>{onSuccessfulCreate?.();await onRefresh?.();onOpenPage(hasCustody?'baby':'members',hasCustody?{baby:child.baby,view:'health'}:{});window.dispatchEvent(new CustomEvent('familyos:children-changed',{detail:{family:family.id}}))}}/>}
    </div>
  </BabySheet>;
}

function queuePetCare(familyId,petId,payload){
  const key=`famuhle-pet-offline:${familyId}`;
  let rows=[];try{rows=JSON.parse(localStorage.getItem(key)||'[]')}catch{rows=[]}
  rows.push({pet:petId,payload});localStorage.setItem(key,JSON.stringify(rows));
}

export function PetCreateSheet({family,onClose,onOpenPage,onSuccessfulCreate}){
  const {t}=useTranslation();
  const [moduleState,setModuleState]=useState(null);
  const [pets,setPets]=useState([]);
  const [selectedIds,setSelectedIds]=useState([]);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  useEffect(()=>{let live=true;(async()=>{
    setModuleState(null);setPets([]);setSelectedIds([]);setError('');
    try{
      const state=await api(`/pets/module/?family=${encodeURIComponent(family.id)}`);
      if(!live)return;setModuleState(state);
      if(!state?.enabled||!state?.authorized)return;
      const data=await api(`/pets/profiles/?family=${encodeURIComponent(family.id)}`);
      if(!live)return;const rows=data.pets||[];setPets(rows);if(rows.length===1)setSelectedIds([rows[0].id]);
    }catch(err){if(live)setError(err.message||t('petUi.error'))}
  })();return()=>{live=false}},[family.id,t]);
  const selectedPet=useMemo(()=>pets.find(row=>String(row.id)===String(selectedIds[0])),[pets,selectedIds]);
  const quickActions=selectedPet?(selectedPet.quick_actions?.length?selectedPet.quick_actions.filter(kind=>PET_QUICK.has(kind)):[...PET_QUICK]):[];
  const canHealth=Boolean(moduleState?.permissions?.health_manage||moduleState?.can_manage);
  async function quick(kind){
    if(!selectedPet)return;
    const payload={kind,occurred_at:now(),value:{},client_event_id:uid()};
    if(!navigator.onLine){queuePetCare(family.id,selectedPet.id,payload);onSuccessfulCreate?.();toast(t('petUi.savedOffline'),{type:'info'});return}
    setBusy(true);setError('');
    try{await api(`/pets/${selectedPet.id}/care/`,{method:'POST',body:JSON.stringify(payload)});onSuccessfulCreate?.();toast(t('petUi.saved'),{type:'success'})}
    catch(err){if(!navigator.onLine){queuePetCare(family.id,selectedPet.id,payload);onSuccessfulCreate?.();toast(t('petUi.savedOffline'),{type:'info'})}else{setError(err.message||t('petUi.error'));toast(err.message||t('petUi.error'),{type:'error'})}}
    finally{setBusy(false)}
  }
  if(!moduleState)return <Sheet family={family} title={t('createUi.pets')} onClose={onClose}><Loading label={t('petUi.loading')}/></Sheet>;
  const chooseRequired=pets.length>1&&!selectedPet;
  return <Sheet family={family} title={t('createUi.pets')} onClose={onClose} busy={busy}>
    <div className="module-create-body">
      <ErrorNotice message={error}/>
      {(!moduleState.enabled||!moduleState.authorized)&&<div className="smart-empty"><Icon name="lock"/><strong>{t('petUi.noAccess')}</strong></div>}
      {moduleState.enabled&&moduleState.authorized&&<>
        {pets.length>1&&<EntityPicker id="pet-create-context" label={t('createUi.choosePet')} description={t('createUi.choosePetHint')} items={pets} selectedIds={selectedIds} onChange={ids=>setSelectedIds(ids.slice(-1))} multiple={false} getItemLabel={pet=>pet.name}/>} 
        {!pets.length&&<div className="smart-empty"><Icon name="pet"/><strong>{t('petUi.empty')}</strong>{moduleState.can_manage&&<button type="button" className="primary" onClick={()=>onOpenPage('pets')}>{t('petUi.addPet')}</button>}</div>}
        {pets.length>0&&<>
          <div className="module-create-actions"><div className="module-create-action-heading"><strong>{t('createUi.petCare')}</strong>{chooseRequired&&<small>{t('createUi.choosePet')}</small>}</div>{quickActions.map(kind=><button type="button" className="secondary" key={kind} disabled={busy||chooseRequired} onClick={()=>quick(kind)}><Icon name={kind==='walk'?'route':'check'}/><span>{t(`petUi.${kind}`)}</span></button>)}</div>
          <div className="module-create-actions"><button type="button" className="secondary" onClick={()=>onOpenPage('pets')}><Icon name="next"/><span>{t('createUi.openPet')}</span></button>{canHealth&&<button type="button" className="secondary" onClick={()=>onOpenPage('pets')}><Icon name="calendar"/><span>{t('createUi.petHealth')}</span></button>}</div>
        </>}
      </>}
    </div>
  </Sheet>;
}
