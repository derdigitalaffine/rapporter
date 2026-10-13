import {useEffect,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import FileDropZone from './FileDropZone';
import {toast} from './feedback';
import {
  ChoiceField,
  ErrorSummary,
  FormActions,
  FormField,
  FormRow,
  FormSection,
  FormShell,
  ProgressiveFieldGroup,
} from './form-primitives';
import './contracts-i18n';
import './contracts.css';

const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const scalar=value=>value&&typeof value==='object'&&'value'in value?value.value:value;
const emptyForm={title:'',category:'',provider:'',contract_number:'',customer_number:'',start_date:'',minimum_term_months:'',end_date:'',cancellation_period:'',renewal_rule:'',amount:'',billing_interval:'',status:'active',notes:'',visibility:'private'};
const fromContract=contract=>({...emptyForm,...Object.fromEntries(Object.keys(emptyForm).map(key=>[key,contract?.[key]??emptyForm[key]]))});
const fieldId=name=>`contract-${name.replaceAll('_','-')}`;

function Evidence({item,t}){
  if(!item)return null;
  return <div className={`contract-evidence ${item.source_type==='derived'?'derived':''}`}>
    <span className="contract-evidence-head">
      <strong>{item.source_type==='derived'?t('contractUi.derived'):t('contractUi.detected')}</strong>
      {Number.isFinite(item.confidence)&&<span>{t('contractUi.confidence',{value:Math.round(item.confidence*100)})}</span>}
      {item.page&&<span>{t('contractUi.page',{page:item.page})}</span>}
    </span>
    {item.evidence_text&&<span>{item.evidence_text}</span>}
  </div>;
}

function Field({label,name,form,setForm,evidence,type='text',t,error='',required=false,...props}){
  const id=fieldId(name);
  return <div className="contract-field">
    <FormField label={label} id={id} error={error} required={required}>
      <input type={type} value={form[name]} onChange={event=>setForm(value=>({...value,[name]:event.target.value}))} {...props}/>
    </FormField>
    <Evidence item={evidence?.[name]} t={t}/>
  </div>;
}

function SelectField({label,name,form,setForm,evidence,t,description='',children}){
  const id=fieldId(name);
  return <div className="contract-field">
    <FormField label={label} id={id} description={description}>
      <select value={form[name]} onChange={event=>setForm(value=>({...value,[name]:event.target.value}))}>{children}</select>
    </FormField>
    <Evidence item={evidence?.[name]} t={t}/>
  </div>;
}

export default function ContractEditor({family,contract=null,onClose,onSaved}){
  const {t}=useTranslation();
  const existing=Boolean(contract?.id);
  const [stage,setStage]=useState(existing?'form':'source');
  const [form,setForm]=useState(()=>fromContract(contract));
  const [draft,setDraft]=useState(contract);
  const [pendingDocument,setPendingDocument]=useState(null);
  const [evidence,setEvidence]=useState({});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [titleError,setTitleError]=useState('');
  const cancelled=useRef(false);

  useEffect(()=>()=>{cancelled.current=true},[]);

  const derived=draft?.derived_dates||[];
  const deadline=derived.find(item=>item.key==='cancellation_deadline');
  const termEnd=derived.find(item=>item.key==='minimum_term_end');
  const documents=useMemo(()=>draft?.documents||[],[draft]);
  const hasDetailEvidence=['contract_number','customer_number','renewal_rule','status','notes'].some(name=>evidence?.[name]);

  function applySuggestions(payload){
    const nextEvidence={};
    setForm(current=>{
      const next={...current};
      for(const suggestion of payload?.suggestions||[]){
        const value=scalar(suggestion.value);
        if(value!==null&&value!==undefined&&value!==''&&!next[suggestion.field])next[suggestion.field]=String(value);
        nextEvidence[suggestion.field]=suggestion;
      }
      return next;
    });
    setEvidence(nextEvidence);
  }

  async function pollPrefill(document){
    for(let attempt=0;attempt<32&&!cancelled.current;attempt++){
      try{
        const result=await api(`/contracts/prefill/?family=${encodeURIComponent(family.id)}&document=${encodeURIComponent(document.id)}`);
        applySuggestions(result);
        if(['review','ready','failed'].includes(result.processing_status)||['review','ready','failed'].includes(result.processing_run?.status)){
          setStage('form');
          return;
        }
      }catch(err){
        if(attempt>2){
          setError(err.message);
          setStage('form');
          return;
        }
      }
      await sleep(attempt<8?500:900);
    }
    if(!cancelled.current)setStage('form');
  }

  async function upload(file){
    if(!file)return;
    setBusy(true);
    setError('');
    try{
      const body=new FormData();
      body.append('family',family.id);
      body.append('file',file);
      body.append('kind','contract');
      body.append('title',file.name||t('contractUi.add'));
      body.append('visibility',form.visibility||'private');
      const document=await api('/documents/',{method:'POST',body});
      setPendingDocument(document);
      if(existing){
        const linked=await api(`/contracts/${contract.id}/documents/`,{method:'POST',body:JSON.stringify({document:document.id})});
        setDraft(linked);
      }
      setStage('processing');
      setBusy(false);
      await pollPrefill(document);
    }catch(err){
      setError(err.message);
      setBusy(false);
      setStage(existing?'form':'source');
    }
  }

  async function removeDocument(documentId){
    if(!draft?.id)return;
    setBusy(true);
    try{
      await api(`/contracts/${draft.id}/documents/${documentId}/`,{method:'DELETE'});
      const fresh=await api(`/contracts/${draft.id}/`);
      setDraft(fresh);
    }catch(err){
      setError(err.message);
    }finally{
      setBusy(false);
    }
  }

  async function save(event){
    event.preventDefault();
    if(!form.title.trim()){
      setTitleError(t('contractUi.titleRequired'));
      setError('');
      return;
    }
    setTitleError('');
    setBusy(true);
    setError('');
    const payload={family:family.id,...form,title:form.title.trim(),minimum_term_months:form.minimum_term_months||null,amount:form.amount||null,start_date:form.start_date||null,end_date:form.end_date||null};
    try{
      let saved=await api(existing?`/contracts/${contract.id}/`:'/contracts/',{method:existing?'PATCH':'POST',body:JSON.stringify(payload)});
      if(pendingDocument&&!saved.documents?.some(item=>String(item.id)===String(pendingDocument.id))){
        saved=await api(`/contracts/${saved.id}/documents/`,{method:'POST',body:JSON.stringify({document:pendingDocument.id})});
      }
      setDraft(saved);
      toast(t('contractUi.saved'),{type:'success'});
      if(existing){
        await onSaved?.(saved);
        onClose();
        return;
      }
      setStage('actions');
    }catch(err){
      setError(err.message);
    }finally{
      setBusy(false);
    }
  }

  async function followUp(action){
    if(!draft?.id)return;
    setBusy(true);
    setError('');
    try{
      await api(`/contracts/${draft.id}/actions/`,{method:'POST',body:JSON.stringify({action,confirmed:true})});
      toast(t('contractUi.confirmed'),{type:'success'});
      await onSaved?.(draft);
      onClose();
    }catch(err){
      setError(err.message);
    }finally{
      setBusy(false);
    }
  }

  async function finish(){
    await onSaved?.(draft);
    onClose();
  }

  const title=existing?t('contractUi.edit'):t('contractUi.newContract');

  return <div className="sheet-backdrop" onMouseDown={event=>event.target===event.currentTarget&&!busy&&onClose()}>
    <section className="quick-sheet contract-sheet" role="dialog" aria-modal="true" aria-labelledby="contract-editor-title">
      <div className="sheet-handle"/>
      <div className="sheet-head">
        <div><small>{family?.name}</small><h2 id="contract-editor-title">{title}</h2></div>
        <button className="sheet-close" type="button" onClick={onClose} disabled={busy} aria-label={t('contractUi.close')}><Icon name="close"/></button>
      </div>

      {stage==='source'&&<div className="contract-actions">
        <p className="contract-source-hint">{t('contractUi.sourceHint')}</p>
        <div className="contract-source-grid">
          <button type="button" className="contract-source-card manual-contract" onClick={()=>setStage('form')}><Icon name="edit"/><strong>{t('contractUi.manual')}</strong></button>
          <FileDropZone className="compact" accept="image/*" capture="environment" icon="camera" title={t('contractUi.scan')} hint="JPG / PNG / WebP" onFiles={files=>upload(files[0])}/>
          <FileDropZone className="compact" accept="application/pdf,image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif" icon="upload" title={t('contractUi.chooseFile')} hint="PDF / Bild" onFiles={files=>upload(files[0])}/>
        </div>
        {error&&<p className="error" role="alert">{error}</p>}
      </div>}

      {stage==='processing'&&<div className="contract-processing" role="status">
        <Icon name="refresh" size={30} className="spin"/>
        <strong>{t('contractUi.processing')}</strong>
        <span>{t('contractUi.sourceHint')}</span>
      </div>}

      {stage==='form'&&<FormShell className="quick-form contract-form" onSubmit={save}>
        {Object.keys(evidence).length>0&&<div className="contract-badge"><Icon name="info"/>{t('contractUi.review')}</div>}
        <ErrorSummary
          errors={titleError?[{id:fieldId('title'),label:t('contractUi.titleField'),message:titleError}]:[]}
          title={t('contractUi.validationSummary')}
        />

        <FormSection legend={t('contractUi.contractSection')}>
          <Field label={t('contractUi.titleField')} name="title" form={form} setForm={setForm} evidence={evidence} t={t} error={titleError} required autoFocus onInvalid={event=>{event.preventDefault();setTitleError(t('contractUi.titleRequired'));setError('')}}/>
          <FormRow>
            <Field label={t('contractUi.provider')} name="provider" form={form} setForm={setForm} evidence={evidence} t={t}/>
            <Field label={t('contractUi.category')} name="category" form={form} setForm={setForm} evidence={evidence} t={t}/>
          </FormRow>
        </FormSection>

        <FormSection legend={t('contractUi.termSection')}>
          <FormRow>
            <Field label={t('contractUi.startDate')} name="start_date" form={form} setForm={setForm} evidence={evidence} t={t} type="date"/>
            <Field label={t('contractUi.endDate')} name="end_date" form={form} setForm={setForm} evidence={evidence} t={t} type="date"/>
          </FormRow>
          <FormRow>
            <Field label={t('contractUi.minimumTerm')} name="minimum_term_months" form={form} setForm={setForm} evidence={evidence} t={t} type="number" min="0" inputMode="numeric"/>
            <Field label={t('contractUi.cancellationPeriod')} name="cancellation_period" form={form} setForm={setForm} evidence={evidence} t={t} placeholder={t('contractUi.cancellationPeriodHint')}/>
          </FormRow>
          {(termEnd||deadline)&&<div className="contract-derived">
            <strong>{t('contractUi.derived')}</strong>
            {termEnd&&<p>{t('contractUi.termEnd',{date:termEnd.date})}</p>}
            {deadline&&<p>{t('contractUi.cancellationDeadline',{date:deadline.date})}</p>}
            <small>{t('contractUi.derivedHint')}</small>
          </div>}
        </FormSection>

        <FormSection legend={t('contractUi.costSection')}>
          <FormRow>
            <Field label={t('contractUi.amount')} name="amount" form={form} setForm={setForm} evidence={evidence} t={t} type="number" step="0.01" min="0" inputMode="decimal"/>
            <SelectField label={t('contractUi.billingInterval')} name="billing_interval" form={form} setForm={setForm} evidence={evidence} t={t}>
              <option value="">—</option>
              {['monthly','quarterly','half_year','yearly','one_time','other'].map(value=><option key={value} value={value}>{t(`contractUi.${value}`)}</option>)}
            </SelectField>
          </FormRow>
        </FormSection>

        <ProgressiveFieldGroup label={t('contractUi.detailsSection')} summary={t('contractUi.detailsSummary')} defaultOpen={hasDetailEvidence}>
          <FormRow>
            <Field label={t('contractUi.contractNumber')} name="contract_number" form={form} setForm={setForm} evidence={evidence} t={t}/>
            <Field label={t('contractUi.customerNumber')} name="customer_number" form={form} setForm={setForm} evidence={evidence} t={t}/>
          </FormRow>
          <Field label={t('contractUi.renewalRule')} name="renewal_rule" form={form} setForm={setForm} evidence={evidence} t={t}/>
          <SelectField label={t('contractUi.status')} name="status" form={form} setForm={setForm} evidence={evidence} t={t}>
            {['active','ending','ended','cancelled','draft'].map(value=><option key={value} value={value}>{t(`contractUi.${value}`)}</option>)}
          </SelectField>
          <FormField label={t('contractUi.notes')} id={fieldId('notes')}>
            <textarea rows="3" value={form.notes} onChange={event=>setForm(value=>({...value,notes:event.target.value}))}/>
          </FormField>
          <Evidence item={evidence?.notes} t={t}/>
          <div className="contract-documents">
            <strong>{t('contractUi.documents')}</strong>
            {documents.map(document=><div className="contract-document-row" key={document.id}>
              <span><Icon name="receipt"/> {document.title}</span>
              <button type="button" className="text-button" disabled={busy} onClick={()=>removeDocument(document.id)}>{t('contractUi.removeDocument')}</button>
            </div>)}
            <FileDropZone className="compact" accept="application/pdf,image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif" icon="upload" title={t('contractUi.addDocument')} hint="PDF / Bild" onFiles={files=>upload(files[0])}/>
          </div>
        </ProgressiveFieldGroup>

        <FormSection legend={t('contractUi.releaseSection')}>
          <ChoiceField
            legend={t('contractUi.visibility')}
            name={fieldId('visibility')}
            value={form.visibility}
            onChange={visibility=>setForm(value=>({...value,visibility}))}
            options={[
              {value:'private',label:t('contractUi.private'),description:t('contractUi.visibilityPrivateHint')},
              {value:'family',label:t('contractUi.family'),description:t('contractUi.visibilityFamilyHint')},
            ]}
          />
        </FormSection>

        {error&&<p className="error" role="alert">{error}</p>}
        <FormActions>
          <button type="submit" className="primary" disabled={busy}>{busy?t('contractUi.saving'):t('contractUi.save')}</button>
        </FormActions>
      </FormShell>}

      {stage==='actions'&&<div className="contract-actions">
        <h3>{t('contractUi.next')}</h3>
        {draft?.visibility!=='family'&&<div className="contract-privacy"><Icon name="lock"/><span>{t('contractUi.familyActionPrivacy')}</span></div>}
        {!deadline&&<p className="contract-source-hint">{t('contractUi.needsDate')}</p>}
        <div className="contract-actions-grid">
          <button type="button" className="secondary" disabled={busy||!deadline} onClick={()=>followUp('reminder')}><Icon name="warning"/>{t('contractUi.reminder')}</button>
          <button type="button" className="secondary" disabled={busy||!deadline||draft?.visibility!=='family'} onClick={()=>followUp('task')}><Icon name="tasks"/>{t('contractUi.task')}</button>
          <button type="button" className="secondary" disabled={busy||!deadline||draft?.visibility!=='family'} onClick={()=>followUp('event')}><Icon name="calendar"/>{t('contractUi.event')}</button>
        </div>
        {error&&<p className="error" role="alert">{error}</p>}
        <button type="button" className="text-button" onClick={finish} disabled={busy}>{t('contractUi.nothing')}</button>
      </div>}
    </section>
  </div>;
}