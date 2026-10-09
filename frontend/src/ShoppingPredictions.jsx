import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import './prediction-i18n';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';
import {SmartShopping} from './SmartLists';
import './shopping-predictions.css';

function PredictionPanel({family,onAccepted}){
 const {t}=useTranslation();const [rows,setRows]=useState([]);const [busy,setBusy]=useState('');
 async function load(){if(!family){setRows([]);return}try{const result=await api(`/shopping-predictions/?family=${encodeURIComponent(family.id)}`);setRows(result?.suggestions||[])}catch{setRows([])}}
 useEffect(()=>{load()},[family?.id]);
 async function accept(row){if(busy)return;setBusy(row.key);try{await api('/shopping-predictions/accept/',{method:'POST',body:JSON.stringify({family:family.id,key:row.key})});toast(t('predictionUi.shoppingAdded',{name:row.name}),{type:'success'});await load();await onAccepted?.()}catch(e){toast(e.message||t('saveFailed'),{type:'error'})}finally{setBusy('')}}
 async function acceptAll(){if(busy)return;setBusy('all');try{const result=await api('/shopping-predictions/accept-all/',{method:'POST',body:JSON.stringify({family:family.id})});toast(t('predictionUi.shoppingAddedAll',{count:result?.created||0}),{type:'success'});await load();await onAccepted?.()}catch(e){toast(e.message||t('saveFailed'),{type:'error'})}finally{setBusy('')}}
 async function dismiss(row){if(busy)return;setBusy(`dismiss:${row.key}`);try{await api('/shopping-predictions/feedback/',{method:'POST',body:JSON.stringify({family:family.id,key:row.key,action:'dismissed'})});setRows(current=>current.filter(item=>item.key!==row.key))}catch(e){toast(e.message||t('saveFailed'),{type:'error'})}finally{setBusy('')}}
 if(!rows.length)return null;
 return <section className="shopping-predictions" aria-labelledby="shopping-predictions-title"><div className="shopping-predictions-head"><div><small>{t('predictionUi.shoppingHint')}</small><h2 id="shopping-predictions-title">{t('predictionUi.shoppingTitle')}</h2></div>{rows.length>1&&<button className="secondary compact" onClick={acceptAll} disabled={!!busy}><Icon name="plus"/>{t('predictionUi.shoppingAddAll')}</button>}</div><div className="shopping-prediction-list">{rows.map(row=><article className="shopping-prediction" key={row.key}><span className="round-icon"><Icon name="shopping"/></span><div className="grow"><strong>{row.name}</strong><small>{t('predictionUi.shoppingReason',{days:row.prediction?.expected_interval_days,since:row.prediction?.days_since_purchase})}</small></div><button className="secondary compact" onClick={()=>accept(row)} disabled={!!busy}><Icon name="plus"/>{t('predictionUi.shoppingAdd')}</button><button className="icon-button" onClick={()=>dismiss(row)} disabled={!!busy} aria-label={`${row.name}: ${t('predictionUi.shoppingDismiss')}`}><Icon name="close"/></button></article>)}</div></section>
}

export default function SmartShoppingPredicted({family,onChanged,...props}){
 const [revision,setRevision]=useState(0);
 async function accepted(){setRevision(value=>value+1);await onChanged?.()}
 return <div className="shopping-prediction-shell"><PredictionPanel family={family} onAccepted={accepted}/><SmartShopping key={`${family?.id||'none'}-${revision}`} family={family} onChanged={onChanged} {...props}/></div>
}
