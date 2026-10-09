import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import bwipjs from 'bwip-js';
import './loyalty-i18n';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import {nativeBarcodeFormats,nativeScannerPlan} from './barcode-scanner';

const formats=['code128','ean13','ean8','upca','upce','code39','itf','qrcode','datamatrix','pdf417','aztec'];
const bcid={code128:'code128',ean13:'ean13',ean8:'ean8',upca:'upca',upce:'upce',code39:'code39',itf:'interleaved2of5',qrcode:'qrcode',datamatrix:'datamatrix',pdf417:'pdf417',aztec:'azteccode'};
const zxingFormats={CODE_128:'code128',EAN_13:'ean13',EAN_8:'ean8',UPC_A:'upca',UPC_E:'upce',CODE_39:'code39',ITF:'itf',QR_CODE:'qrcode',DATA_MATRIX:'datamatrix',PDF_417:'pdf417',AZTEC:'aztec'};

function BarcodePreview({value,format,t}){const ref=useRef(null);const [error,setError]=useState('');useEffect(()=>{setError('');if(!value||!format||!ref.current)return;try{bwipjs.toCanvas(ref.current,{bcid:bcid[format]||'code128',text:String(value),scale:3,height:['qrcode','datamatrix','aztec'].includes(format)?34:18,includetext:!['qrcode','datamatrix','pdf417','aztec'].includes(format),textxalign:'center',paddingwidth:10,paddingheight:10,backgroundcolor:'FFFFFF'})}catch{setError(t('loyaltyUi.formatUnsupported'))}},[value,format,t]);return <div className="barcode-stage">{error?<div className="barcode-fallback">{error}<br/>{value}</div>:<canvas ref={ref} aria-label={`${t('loyaltyUi.barcodeFormat')}: ${t(`loyaltyUi.formats.${format}`)}`}/>}</div>}

function Scanner({onDetected,onClose,t}){
 const video=useRef(null);const [error,setError]=useState('');const [ready,setReady]=useState(false);const [fallbackActive,setFallbackActive]=useState(false);
 useEffect(()=>{let stopped=false,stream=null,controls=null,timer=null,nativeRunning=false;
  async function finish(raw,format){if(stopped||!raw)return;stopped=true;if(timer)clearTimeout(timer);try{controls?.stop?.()}catch{}if(stream)stream.getTracks().forEach(track=>track.stop());onDetected({value:raw,format:format||'code128'})}
  async function startFallback(){
   try{
    const [{BrowserMultiFormatReader},{BarcodeFormat,DecodeHintType}]=await Promise.all([import('@zxing/browser'),import('@zxing/library')]);
    const possible=[BarcodeFormat.CODE_128,BarcodeFormat.EAN_13,BarcodeFormat.EAN_8,BarcodeFormat.UPC_A,BarcodeFormat.UPC_E,BarcodeFormat.CODE_39,BarcodeFormat.ITF,BarcodeFormat.QR_CODE,BarcodeFormat.DATA_MATRIX,BarcodeFormat.PDF_417,BarcodeFormat.AZTEC];
    const hints=new Map();hints.set(DecodeHintType.POSSIBLE_FORMATS,possible);hints.set(DecodeHintType.TRY_HARDER,true);
    const reader=new BrowserMultiFormatReader(hints);
    setFallbackActive(true);
    controls=await reader.decodeFromStream(stream,video.current,result=>{if(!result)return;const key=BarcodeFormat[result.getBarcodeFormat()];finish(result.getText(),zxingFormats[key]||'code128')});
   }catch{if(!nativeRunning)setError(t('loyaltyUi.cameraDenied'))}
  }
  async function start(){
   try{
    if(!navigator.mediaDevices?.getUserMedia)throw new Error('camera');
    stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}},audio:false});
    if(stopped)return;video.current.srcObject=stream;await video.current.play();setReady(true);
    let plan={accepted:[],oneDimensionalComplete:false,useFallback:true};
    if('BarcodeDetector'in window){
     let supported=[];try{supported=await window.BarcodeDetector.getSupportedFormats()}catch{}
     plan=nativeScannerPlan(supported);
     if(plan.accepted.length){
      nativeRunning=true;const detector=new window.BarcodeDetector({formats:plan.accepted});
      const poll=async()=>{if(stopped)return;try{const rows=await detector.detect(video.current);if(rows[0])return finish(rows[0].rawValue,nativeBarcodeFormats[rows[0].format]||'code128')}catch{}timer=setTimeout(poll,160)};poll();
     }
    }
    // A browser may expose BarcodeDetector but only implement QR. Keep ZXing active
    // whenever EAN-13/EAN-8/Code128 are not all available natively.
    if(plan.useFallback||!nativeRunning)await startFallback();
   }catch{setError(t('loyaltyUi.cameraDenied'))}
  }
  start();return()=>{stopped=true;if(timer)clearTimeout(timer);try{controls?.stop?.()}catch{}if(stream)stream.getTracks().forEach(track=>track.stop())}
 },[onDetected,t]);
 return <div className="sheet-backdrop"><section className="quick-sheet" role="dialog" aria-modal="true"><div className="sheet-handle"/><div className="sheet-head"><h2>{t('loyaltyUi.scannerTitle')}</h2><button className="sheet-close" onClick={onClose} aria-label={t('back')}><Icon name="close"/></button></div><p className="scanner-copy">{t('loyaltyUi.scannerHint')}</p><div className="scanner-stage"><video ref={video} muted playsInline/><div className="scanner-frame"/>{!ready&&!error&&<span className="sr-only">…</span>}</div>{fallbackActive&&<p className="scanner-copy" role="status">{t('loyaltyUi.scannerFallbackActive')}</p>}{error&&<div className="scanner-error">{error}</div>}<button className="secondary" onClick={onClose}>{t('loyaltyUi.manualFallback')}</button></section></div>
}

export default function LoyaltyCardEditor({family,card=null,onClose,onSaved}){
 const {t}=useTranslation();const initial=card||{name:'',logo:'',color:'#6750A4',holder_name:'',holder_membership:null,customer_number:'',barcode_value:'',barcode_format:'code128',note:'',favorite:false,shared_with:[]};
 const [form,setForm]=useState({...initial,shared_with_ids:(initial.shared_with||[]).map(member=>member.id)});const [busy,setBusy]=useState(false);const [scanner,setScanner]=useState(false);const members=family?.memberships||[];const allIds=members.map(member=>String(member.id));const allShared=allIds.length>0&&allIds.every(id=>(form.shared_with_ids||[]).map(String).includes(id));
 function set(key,value){setForm(current=>({...current,[key]:value}))}function toggleMember(id){const values=(form.shared_with_ids||[]).map(String);set('shared_with_ids',values.includes(String(id))?values.filter(value=>value!==String(id)):[...values,String(id)])}
 async function save(event){event.preventDefault();setBusy(true);try{const payload={family:family.id,name:form.name.trim(),logo:form.logo||'',color:form.color||'#6750A4',holder_name:form.holder_name||'',holder_membership:form.holder_membership||null,customer_number:form.customer_number||'',barcode_value:form.barcode_value.trim(),barcode_format:form.barcode_format,note:form.note||'',favorite:!!form.favorite,shared_with_ids:form.shared_with_ids||[]};const saved=await api(card?.id?`/loyalty-cards/${card.id}/`:'/loyalty-cards/',{method:card?.id?'PATCH':'POST',body:JSON.stringify(payload)});toast(t('loyaltyUi.saved'),{type:'success'});await onSaved(saved)}catch(error){toast(error.message||t('saveFailed'),{type:'error'});setBusy(false)}}
 return <><div className="sheet-backdrop"><section className="quick-sheet loyalty-editor" role="dialog" aria-modal="true"><div className="sheet-handle"/><div className="sheet-head"><h2>{card?.id?t('loyaltyUi.edit'):t('loyaltyUi.add')}</h2><button className="sheet-close" onClick={onClose} disabled={busy} aria-label={t('back')}><Icon name="close"/></button></div><form className="quick-form" onSubmit={save}><div className="push-actions"><button type="button" className="secondary" onClick={()=>setScanner(true)}><Icon name="search"/>{t('loyaltyUi.scan')}</button></div><div className="loyalty-form-grid"><label>{t('loyaltyUi.name')}<input value={form.name} onChange={event=>set('name',event.target.value)} required autoFocus/></label><label>{t('loyaltyUi.logo')}<input value={form.logo||''} onChange={event=>set('logo',event.target.value)} maxLength="8" placeholder="★"/></label><label>{t('loyaltyUi.color')}<input type="color" value={/^#[0-9a-f]{6}$/i.test(form.color||'')?form.color:'#6750A4'} onChange={event=>set('color',event.target.value)}/></label><label>{t('loyaltyUi.holder')}<input value={form.holder_name||''} onChange={event=>set('holder_name',event.target.value)}/></label></div><label>{t('loyaltyUi.holderMember')}<select value={form.holder_membership||''} onChange={event=>set('holder_membership',event.target.value||null)}><option value="">—</option>{members.map(member=><option value={member.id} key={member.id}>{member.display_name||member.username}</option>)}</select></label><label>{t('loyaltyUi.customerNumber')}<input value={form.customer_number||''} onChange={event=>set('customer_number',event.target.value)}/></label><div className="loyalty-form-grid"><label>{t('loyaltyUi.barcodeFormat')}<select value={form.barcode_format} onChange={event=>set('barcode_format',event.target.value)}>{formats.map(format=><option value={format} key={format}>{t(`loyaltyUi.formats.${format}`)}</option>)}</select></label><label>{t('loyaltyUi.barcodeValue')}<input value={form.barcode_value||''} onChange={event=>set('barcode_value',event.target.value)} required autoComplete="off"/></label></div>{form.barcode_value&&<div className="loyalty-code-preview"><BarcodePreview value={form.barcode_value} format={form.barcode_format} t={t}/></div>}<label>{t('loyaltyUi.note')}<textarea value={form.note||''} onChange={event=>set('note',event.target.value)}/></label><label className="toggle-label"><input type="checkbox" checked={!!form.favorite} onChange={event=>set('favorite',event.target.checked)}/>{t('loyaltyUi.favorite')}</label><fieldset><legend>{t('loyaltyUi.sharing')}</legend><p className="page-intro">{t('loyaltyUi.sharingHint')}</p><label className="toggle-label"><input type="checkbox" checked={allShared} onChange={event=>set('shared_with_ids',event.target.checked?allIds:[])}/>{t('loyaltyUi.shareAll')}</label><div className="sharing-list">{members.map(member=><label className="sharing-row" key={member.id}><input type="checkbox" checked={(form.shared_with_ids||[]).map(String).includes(String(member.id))} onChange={()=>toggleMember(member.id)}/><span>{member.display_name||member.username} · {member.role}</span></label>)}</div>{!(form.shared_with_ids||[]).length&&<small>{t('loyaltyUi.onlyMe')}</small>}</fieldset><button className="primary" disabled={busy||!form.name.trim()||!form.barcode_value.trim()}><Icon name="check"/>{busy?t('pleaseWait'):t('loyaltyUi.save')}</button></form></section></div>{scanner&&<Scanner t={t} onClose={()=>setScanner(false)} onDetected={({value,format})=>{setForm(current=>({...current,barcode_value:value,barcode_format:format}));setScanner(false);toast(t('loyaltyUi.detected'),{type:'success'})}}/>}</>
}
