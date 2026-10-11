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
const fallbackTypes=['loyalty_card','voucher','coupon','ticket','boarding_pass'];
const fallbackCatalog={
  pass_types:fallbackTypes.map(value=>({value,label:value})),
  icons:[],
  color_modes:['custom','auto'],
  undo_window:{default_minutes:10,min_minutes:1,max_minutes:1440},
};
const eventTypes=new Set(['ticket','boarding_pass']);

function toLocalDateTime(value){
  if(!value)return'';
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return'';
  const local=new Date(date.getTime()-date.getTimezoneOffset()*60000);
  return local.toISOString().slice(0,16);
}

function toIso(value){
  if(!value)return null;
  const date=new Date(value);
  return Number.isNaN(date.getTime())?null:date.toISOString();
}

function BarcodePreview({value,format,t}){
  const ref=useRef(null);
  const [error,setError]=useState('');
  useEffect(()=>{
    setError('');
    if(!value||!format||!ref.current)return;
    try{
      bwipjs.toCanvas(ref.current,{bcid:bcid[format]||'code128',text:String(value),scale:3,height:['qrcode','datamatrix','aztec'].includes(format)?34:18,includetext:!['qrcode','datamatrix','pdf417','aztec'].includes(format),textxalign:'center',paddingwidth:10,paddingheight:10,backgroundcolor:'FFFFFF'});
    }catch{
      setError(t('loyaltyUi.formatUnsupported'));
    }
  },[value,format,t]);
  return <div className="barcode-stage">{error?<div className="barcode-fallback">{error}<br/>{value}</div>:<canvas ref={ref} aria-label={`${t('loyaltyUi.barcodeFormat')}: ${t(`loyaltyUi.formats.${format}`)}`}/>}</div>;
}

function Scanner({onDetected,onClose,t}){
  const video=useRef(null);
  const [error,setError]=useState('');
  const [ready,setReady]=useState(false);
  const [fallbackActive,setFallbackActive]=useState(false);

  useEffect(()=>{
    let stopped=false,stream=null,controls=null,timer=null,nativeRunning=false;

    async function finish(raw,format){
      if(stopped||!raw)return;
      stopped=true;
      if(timer)clearTimeout(timer);
      try{controls?.stop?.()}catch{}
      if(stream)stream.getTracks().forEach(track=>track.stop());
      onDetected({value:raw,format:format||'code128'});
    }

    async function startFallback(){
      try{
        const [{BrowserMultiFormatReader},{BarcodeFormat,DecodeHintType}]=await Promise.all([import('@zxing/browser'),import('@zxing/library')]);
        const possible=[BarcodeFormat.CODE_128,BarcodeFormat.EAN_13,BarcodeFormat.EAN_8,BarcodeFormat.UPC_A,BarcodeFormat.UPC_E,BarcodeFormat.CODE_39,BarcodeFormat.ITF,BarcodeFormat.QR_CODE,BarcodeFormat.DATA_MATRIX,BarcodeFormat.PDF_417,BarcodeFormat.AZTEC];
        const hints=new Map();
        hints.set(DecodeHintType.POSSIBLE_FORMATS,possible);
        hints.set(DecodeHintType.TRY_HARDER,true);
        const reader=new BrowserMultiFormatReader(hints);
        setFallbackActive(true);
        controls=await reader.decodeFromStream(stream,video.current,result=>{
          if(!result)return;
          const key=BarcodeFormat[result.getBarcodeFormat()];
          finish(result.getText(),zxingFormats[key]||'code128');
        });
      }catch{
        if(!nativeRunning)setError(t('loyaltyUi.cameraDenied'));
      }
    }

    async function start(){
      try{
        if(!navigator.mediaDevices?.getUserMedia)throw new Error('camera');
        stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}},audio:false});
        if(stopped)return;
        video.current.srcObject=stream;
        await video.current.play();
        setReady(true);
        let plan={accepted:[],oneDimensionalComplete:false,useFallback:true};
        if('BarcodeDetector'in window){
          let supported=[];
          try{supported=await window.BarcodeDetector.getSupportedFormats()}catch{}
          plan=nativeScannerPlan(supported);
          if(plan.accepted.length){
            nativeRunning=true;
            const detector=new window.BarcodeDetector({formats:plan.accepted});
            const poll=async()=>{
              if(stopped)return;
              try{
                const rows=await detector.detect(video.current);
                if(rows[0])return finish(rows[0].rawValue,nativeBarcodeFormats[rows[0].format]||'code128');
              }catch{}
              timer=setTimeout(poll,160);
            };
            poll();
          }
        }
        if(plan.useFallback||!nativeRunning)await startFallback();
      }catch{
        setError(t('loyaltyUi.cameraDenied'));
      }
    }

    start();
    return()=>{
      stopped=true;
      if(timer)clearTimeout(timer);
      try{controls?.stop?.()}catch{}
      if(stream)stream.getTracks().forEach(track=>track.stop());
    };
  },[onDetected,t]);

  return <div className="sheet-backdrop">
    <section className="quick-sheet" role="dialog" aria-modal="true">
      <div className="sheet-handle"/>
      <div className="sheet-head"><h2>{t('loyaltyUi.scannerTitle')}</h2><button className="sheet-close" onClick={onClose} aria-label={t('back')}><Icon name="close"/></button></div>
      <p className="scanner-copy">{t('loyaltyUi.scannerHint')}</p>
      <div className="scanner-stage"><video ref={video} muted playsInline/><div className="scanner-frame"/>{!ready&&!error&&<span className="sr-only">…</span>}</div>
      {fallbackActive&&<p className="scanner-copy" role="status">{t('loyaltyUi.scannerFallbackActive')}</p>}
      {error&&<div className="scanner-error">{error}</div>}
      <button className="secondary" onClick={onClose}>{t('loyaltyUi.manualFallback')}</button>
    </section>
  </div>;
}

export default function LoyaltyCardEditor({family,card=null,onClose,onSaved}){
  const {t,i18n}=useTranslation();
  const initial=card||{name:'',pass_type:'loyalty_card',icon_key:'card',logo:'',color:'#6750A4',color_mode:'auto',holder_name:'',holder_membership:null,customer_number:'',barcode_value:'',barcode_format:'code128',note:'',favorite:false,shared_with:[],undo_window_minutes:10,event_ends_at:null};
  const [form,setForm]=useState({...initial,event_ends_at:toLocalDateTime(initial.event_ends_at),shared_with_ids:(initial.shared_with||[]).map(member=>member.id)});
  const [catalog,setCatalog]=useState(fallbackCatalog);
  const [busy,setBusy]=useState(false);
  const [scanner,setScanner]=useState(false);
  const members=family?.memberships||[];
  const allIds=members.map(member=>String(member.id));
  const allShared=allIds.length>0&&allIds.every(id=>(form.shared_with_ids||[]).map(String).includes(id));

  useEffect(()=>{
    let active=true;
    api('/loyalty-cards/catalog/').then(value=>{
      if(active&&value&&Array.isArray(value.pass_types)&&Array.isArray(value.icons))setCatalog({...fallbackCatalog,...value});
    }).catch(()=>{});
    return()=>{active=false};
  },[]);

  function set(key,value){setForm(current=>({...current,[key]:value}));}
  function toggleMember(id){
    const values=(form.shared_with_ids||[]).map(String);
    set('shared_with_ids',values.includes(String(id))?values.filter(value=>value!==String(id)):[...values,String(id)]);
  }

  const passTypes=(catalog.pass_types||fallbackCatalog.pass_types).map(row=>typeof row==='string'?row:row.value);
  const iconGroups=(catalog.icons||[]).reduce((groups,row)=>{(groups[row.group]||(groups[row.group]=[])).push(row);return groups;},{});
  const selectedIcon=(catalog.icons||[]).find(row=>row.key===form.icon_key);
  const minUndo=catalog.undo_window?.min_minutes||1;
  const maxUndo=catalog.undo_window?.max_minutes||1440;

  async function save(event){
    event.preventDefault();
    setBusy(true);
    try{
      const payload={
        family:family.id,
        name:form.name.trim(),
        pass_type:form.pass_type||'loyalty_card',
        icon_key:form.icon_key||'',
        color:form.color||'#6750A4',
        color_mode:form.color_mode||'custom',
        holder_name:form.holder_name||'',
        holder_membership:form.holder_membership||null,
        customer_number:form.customer_number||'',
        barcode_value:form.barcode_value.trim(),
        barcode_format:form.barcode_format,
        note:form.note||'',
        favorite:!!form.favorite,
        shared_with_ids:form.shared_with_ids||[],
        undo_window_minutes:Number(form.undo_window_minutes)||10,
        event_ends_at:eventTypes.has(form.pass_type)?toIso(form.event_ends_at):null,
      };
      const saved=await api(card?.id?`/loyalty-cards/${card.id}/`:'/loyalty-cards/',{method:card?.id?'PATCH':'POST',body:JSON.stringify(payload)});
      toast(t('loyaltyUi.saved'),{type:'success'});
      await onSaved(saved);
    }catch(error){
      toast(error.message||t('saveFailed'),{type:'error'});
      setBusy(false);
    }
  }

  return <>
    <div className="sheet-backdrop">
      <section className="quick-sheet loyalty-editor" role="dialog" aria-modal="true">
        <div className="sheet-handle"/>
        <div className="sheet-head"><h2>{card?.id?t('loyaltyUi.edit'):t('loyaltyUi.add')}</h2><button className="sheet-close" onClick={onClose} disabled={busy} aria-label={t('back')}><Icon name="close"/></button></div>
        <form className="quick-form" onSubmit={save}>
          <div className="push-actions"><button type="button" className="secondary" onClick={()=>setScanner(true)}><Icon name="search"/>{t('loyaltyUi.scan')}</button></div>
          <div className="loyalty-form-grid">
            <label>{t('loyaltyUi.name')}<input value={form.name} onChange={event=>set('name',event.target.value)} required autoFocus/></label>
            <label>{t('loyaltyUi.passType')}<select value={form.pass_type||'loyalty_card'} onChange={event=>set('pass_type',event.target.value)}>{passTypes.map(value=><option value={value} key={value}>{t(`loyaltyUi.types.${value}`)}</option>)}</select></label>
          </div>
          <label>{t('loyaltyUi.icon')}<select value={form.icon_key||''} onChange={event=>set('icon_key',event.target.value)}><option value="">—</option>{Object.entries(iconGroups).map(([group,rows])=><optgroup label={t(`loyaltyUi.iconGroups.${group}`)} key={group}>{rows.map(row=><option value={row.key} key={row.key}>{row.glyph} {i18n.language?.startsWith('de')?row.label_de:row.label_en}</option>)}</optgroup>)}</select></label>
          {selectedIcon&&<div className="registry-preview" style={{'--preview-accent':selectedIcon.accent}}><span aria-hidden="true">{selectedIcon.glyph}</span><strong>{i18n.language?.startsWith('de')?selectedIcon.label_de:selectedIcon.label_en}</strong></div>}
          {card?.logo&&!card?.icon_key&&<div className="legacy-icon-note"><span aria-hidden="true">{card.logo}</span><span>{t('loyaltyUi.legacyIcon')}</span></div>}
          <fieldset>
            <legend>{t('loyaltyUi.colorMode')}</legend>
            <div className="color-mode-row"><label className="toggle-label"><input type="radio" name="pass-color-mode" value="auto" checked={form.color_mode==='auto'} onChange={()=>set('color_mode','auto')}/>{t('loyaltyUi.colorAuto')}</label><label className="toggle-label"><input type="radio" name="pass-color-mode" value="custom" checked={form.color_mode!=='auto'} onChange={()=>set('color_mode','custom')}/>{t('loyaltyUi.colorCustom')}</label></div>
            {form.color_mode!=='auto'&&<label>{t('loyaltyUi.color')}<input type="color" value={/^#[0-9a-f]{6}$/i.test(form.color||'')?form.color:'#6750A4'} onChange={event=>set('color',event.target.value)}/></label>}
          </fieldset>
          <div className="loyalty-form-grid">
            <label>{t('loyaltyUi.holder')}<input value={form.holder_name||''} onChange={event=>set('holder_name',event.target.value)}/></label>
            <label>{t('loyaltyUi.holderMember')}<select value={form.holder_membership||''} onChange={event=>set('holder_membership',event.target.value||null)}><option value="">—</option>{members.map(member=><option value={member.id} key={member.id}>{member.display_name||member.username}</option>)}</select></label>
          </div>
          <label>{t('loyaltyUi.customerNumber')}<input value={form.customer_number||''} onChange={event=>set('customer_number',event.target.value)}/></label>
          <div className="loyalty-form-grid">
            <label>{t('loyaltyUi.barcodeFormat')}<select value={form.barcode_format} onChange={event=>set('barcode_format',event.target.value)}>{formats.map(format=><option value={format} key={format}>{t(`loyaltyUi.formats.${format}`)}</option>)}</select></label>
            <label>{t('loyaltyUi.barcodeValue')}<input value={form.barcode_value||''} onChange={event=>set('barcode_value',event.target.value)} required autoComplete="off"/></label>
          </div>
          {form.barcode_value&&<div className="loyalty-code-preview"><BarcodePreview value={form.barcode_value} format={form.barcode_format} t={t}/></div>}
          {form.pass_type!=='loyalty_card'&&<label>{t('loyaltyUi.undoWindow')}<input type="number" min={minUndo} max={maxUndo} value={form.undo_window_minutes||10} onChange={event=>set('undo_window_minutes',event.target.value)}/><small>{t('loyaltyUi.undoMinutes')}</small></label>}
          {eventTypes.has(form.pass_type)&&<label>{t('loyaltyUi.eventEnds')}<input type="datetime-local" value={form.event_ends_at||''} onChange={event=>set('event_ends_at',event.target.value)}/></label>}
          <label>{t('loyaltyUi.note')}<textarea value={form.note||''} onChange={event=>set('note',event.target.value)}/></label>
          <label className="toggle-label"><input type="checkbox" checked={!!form.favorite} onChange={event=>set('favorite',event.target.checked)}/>{t('loyaltyUi.favorite')}</label>
          <fieldset>
            <legend>{t('loyaltyUi.sharing')}</legend>
            <p className="page-intro">{t('loyaltyUi.sharingHint')}</p>
            <label className="toggle-label"><input type="checkbox" checked={allShared} onChange={event=>set('shared_with_ids',event.target.checked?allIds:[])}/>{t('loyaltyUi.shareAll')}</label>
            <div className="sharing-list">{members.map(member=><label className="sharing-row" key={member.id}><input type="checkbox" checked={(form.shared_with_ids||[]).map(String).includes(String(member.id))} onChange={()=>toggleMember(member.id)}/><span>{member.display_name||member.username} · {member.role}</span></label>)}</div>
            {!(form.shared_with_ids||[]).length&&<small>{t('loyaltyUi.onlyMe')}</small>}
          </fieldset>
          <button className="primary" disabled={busy||!form.name.trim()||!form.barcode_value.trim()}><Icon name="check"/>{busy?t('pleaseWait'):t('loyaltyUi.save')}</button>
        </form>
      </section>
    </div>
    {scanner&&<Scanner t={t} onClose={()=>setScanner(false)} onDetected={({value,format})=>{setForm(current=>({...current,barcode_value:value,barcode_format:format}));setScanner(false);toast(t('loyaltyUi.detected'),{type:'success'});}}/>}
  </>;
}
