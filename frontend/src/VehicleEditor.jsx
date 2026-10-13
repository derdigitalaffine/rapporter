import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {FormShell,FormField,FormSection,FormActions,ProgressiveFieldGroup,ErrorSummary} from './form-primitives';
import './vehicles-i18n';
import './vehicles.css';

export function vehicleError(error,t){
 const code=error?.code||error?.message;
 return t(`vehiclesUi.${code}`,{defaultValue:error?.status===403||error?.status===404?t('vehiclesUi.forbidden'):t('vehiclesUi.error')});
}

export default function VehicleEditor({family,vehicle=null,fuel=false,onClose,onSaved}){
 const {t}=useTranslation();const dialog=useRef(null);const alive=useRef(true);
 const [busy,setBusy]=useState(false);const [error,setError]=useState('');const [fields,setFields]=useState({});
 const [form,setForm]=useState(()=>fuel?{request_id:crypto.randomUUID(),date:new Date().toLocaleDateString('sv-SE'),odometer:vehicle?.odometer||0,quantity:'',unit:vehicle?.fuel_type==='electric'?'kWh':'l',total_cost:'',currency:'EUR',station:'',full_tank:true}:{name:'',plate:'',manufacturer:'',model:'',vin:'',first_registration:'',fuel_type:'petrol',odometer:0,notes:'',archived:false,...vehicle});
 useEffect(()=>{alive.current=true;const previous=document.activeElement;dialog.current?.querySelector('input')?.focus();return()=>{alive.current=false;previous?.focus()}},[]);
 async function save(event){event.preventDefault();if(busy)return;setBusy(true);setError('');setFields({});try{const body={...form};delete body.id;delete body.family;if(!fuel)body.first_registration=body.first_registration||null;const record=await api(fuel?`/vehicles/${vehicle.id}/fuel/`:`/vehicles/${vehicle?`${vehicle.id}/`:`?family=${encodeURIComponent(family.id)}`}`,{method:!fuel&&vehicle?'PATCH':'POST',body:JSON.stringify(body)});if(alive.current)await onSaved(record)}catch(e){if(alive.current){setError(vehicleError(e,t));setFields(e.payload||{})}}finally{if(alive.current)setBusy(false)}}
 const field=(name,type='text',required=false,props={})=><FormField key={name} id={`vehicle-${name}`} label={t(`vehiclesUi.${name}`)} required={required} error={fields[name]?vehicleError({message:Array.isArray(fields[name])?fields[name][0]:fields[name]},t):''}><input type={type} value={form[name]} onChange={e=>setForm({...form,[name]:e.target.value})} {...props}/></FormField>;
 return <div className="sheet-backdrop" onMouseDown={e=>e.target===e.currentTarget&&!busy&&onClose()}><section ref={dialog} className="quick-sheet vehicle-editor" role="dialog" aria-modal="true" aria-labelledby="vehicle-editor-title"><div className="sheet-handle"/><div className="sheet-head"><h2 id="vehicle-editor-title">{t(`vehiclesUi.${fuel?'addFuel':vehicle?'edit':'add'}`)}</h2><button className="sheet-close" type="button" disabled={busy} onClick={onClose} aria-label={t('vehiclesUi.cancel')}><Icon name="close"/></button></div><FormShell onSubmit={save}>
 {error&&<ErrorSummary title={error} errors={[{id:'vehicle-'+(Object.keys(fields).find(key=>key in form)||'odometer'),message:error}]}/>}
 <FormSection legend={t(`vehiclesUi.${fuel?'fuel':'vehicle'}`)}>{fuel?<>{field('date','date',true)}{field('odometer','number',true,{min:0,step:'0.1'})}{field('quantity','number',true,{min:'0.001',step:'0.001'})}<FormField label={t('vehiclesUi.unit')}><select value={form.unit} onChange={e=>setForm({...form,unit:e.target.value})}><option value="l">l</option><option value="kWh">kWh</option></select></FormField>{field('total_cost','number',true,{min:0,step:'0.01'})}</>:<>{field('name','text',true,{maxLength:120})}{field('plate','text',false,{maxLength:24})}{field('odometer','number',true,{min:0,step:'0.1'})}<FormField label={t('vehiclesUi.fuel_type')}><select value={form.fuel_type} onChange={e=>setForm({...form,fuel_type:e.target.value})}>{['petrol','diesel','electric','hybrid','other'].map(key=><option key={key} value={key}>{t(`vehiclesUi.${key}`)}</option>)}</select></FormField></>}</FormSection>
 <ProgressiveFieldGroup label={t('vehiclesUi.details')}>{fuel?<>{field('currency','text',true,{minLength:3,maxLength:3})}{field('station','text',false,{maxLength:160})}<label className="vehicle-checkbox"><input type="checkbox" checked={form.full_tank} onChange={e=>setForm({...form,full_tank:e.target.checked})}/>{t('vehiclesUi.full_tank')}</label></>:<>{field('manufacturer','text',false,{maxLength:80})}{field('model','text',false,{maxLength:80})}{field('vin','text',false,{maxLength:17})}{field('first_registration','date')}<FormField label={t('vehiclesUi.notes')}><textarea maxLength={2000} value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})}/></FormField>{vehicle&&<label className="vehicle-checkbox"><input type="checkbox" checked={form.archived} onChange={e=>setForm({...form,archived:e.target.checked})}/>{t('vehiclesUi.archived')}</label>}</>}</ProgressiveFieldGroup>
 <FormActions><button className="primary" type="submit" disabled={busy}>{t(`vehiclesUi.${busy?'loading':'save'}`)}</button><button className="secondary" type="button" disabled={busy} onClick={onClose}>{t('vehiclesUi.cancel')}</button></FormActions></FormShell></section></div>;
}
