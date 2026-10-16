import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import './receipt-intelligence-i18n';
import './receipt-intelligence.css';

const FIELD_LABELS={time:'time',receipt_id:'receiptId',subtotal:'subtotal',tax:'tax'};
const REASON_KEYS={
 ocr_confidence_low:'ocr_confidence_low',
 total_missing:'total_missing',
 total_confidence_low:'total_confidence_low',
 total_ambiguous:'total_ambiguous',
 reconciliation_mismatch:'reconciliation_mismatch',
};

function percent(value){const number=Number(value);return Number.isFinite(number)?Math.round(Math.max(0,Math.min(1,number))*100):null}
function toneFor(value){const number=Number(value);if(!Number.isFinite(number))return'';if(number>=.82)return'good';if(number>=.55)return'warn';return'low'}
function money(value,currency,locale){if(value===null||value===undefined||value==='')return'';const number=Number(value);if(!Number.isFinite(number))return String(value);try{return new Intl.NumberFormat(locale||'de',{style:'currency',currency:currency||'EUR'}).format(number)}catch{return `${number.toFixed(2)} ${currency||''}`.trim()}}
function evidenceValue(entry){return entry?.normalized??entry?.value??''}

function Signal({label,value,t}){
 const pct=percent(value);const tone=toneFor(value);
 return <div className={`receipt-intelligence-signal ${tone}`}><span>{label}</span><strong>{pct===null?t('receiptIntelligence.notAvailable'):`${pct}%`}</strong><div className="receipt-intelligence-meter" aria-hidden="true"><span style={{width:`${pct||0}%`}}/></div></div>;
}

export default function ReceiptIntelligenceReview({extraction,currency='EUR'}){
 const {t,i18n}=useTranslation();
 const data=extraction?.structured_data||{};
 if(Number(data.schema_version||0)<2)return null;
 const fields=data.fields||{};
 const review=data.review||{};
 const reasons=Array.isArray(review.reasons)?review.reasons:[];
 const reconciliation=data.reconciliation||{};
 const items=Array.isArray(data.line_items)?data.line_items:[];
 const candidates=Array.isArray(data.total_candidates)?data.total_candidates:[];
 const facts=[
  ['time',evidenceValue(fields.time),extraction?.field_confidences?.time],
  ['receipt_id',evidenceValue(fields.receipt_id),extraction?.field_confidences?.receipt_id],
  ['subtotal',extraction?.subtotal??evidenceValue(fields.subtotal),extraction?.field_confidences?.subtotal],
  ['tax',extraction?.tax??evidenceValue(fields.tax),extraction?.field_confidences?.tax],
 ].filter(([,value])=>value!==null&&value!==undefined&&value!=='');
 const evidence=Object.entries(fields).filter(([,entry])=>entry?.raw||entry?.normalized);
 const status=reconciliation.status||'insufficient';
 return <section className="receipt-intelligence" aria-labelledby="receipt-intelligence-title">
  <div className="receipt-intelligence-head"><div><h3 id="receipt-intelligence-title">{t('receiptIntelligence.title')}</h3><p>{t('receiptIntelligence.subtitle')}</p></div><span className="receipt-intelligence-version">{data.extractor_version||`v${data.schema_version}`}</span></div>
  <div className="receipt-intelligence-signals"><Signal label={t('receiptIntelligence.ocrConfidence')} value={data.ocr_confidence} t={t}/><Signal label={t('receiptIntelligence.semanticConfidence')} value={data.semantic_confidence} t={t}/></div>
  <div className={`receipt-intelligence-review ${review.needs_review?'warn':''}`}><strong><Icon name={review.needs_review?'warning':'check'} size={16}/>{review.needs_review?t('receiptIntelligence.reviewNeeded'):t('receiptIntelligence.reviewClear')}</strong>{reasons.length>0&&<ul>{reasons.map(reason=><li key={reason}>{t(`receiptIntelligence.reasons.${REASON_KEYS[reason]||reason}`,{defaultValue:reason})}</li>)}</ul>}</div>
  {facts.length>0&&<dl className="receipt-intelligence-facts">{facts.map(([key,value,confidence])=><div className="receipt-intelligence-fact" key={key}><dt>{t(`receiptIntelligence.${FIELD_LABELS[key]}`)}</dt><dd>{key==='subtotal'||key==='tax'?money(value,currency,i18n.language):String(value)}</dd>{percent(confidence)!==null&&<small>{t('receiptIntelligence.confidence')}: {percent(confidence)}%</small>}</div>)}</dl>}
  <div className={`receipt-reconciliation ${status}`}><strong><Icon name={status==='mismatch'?'warning':status==='matched'?'check':'info'} size={16}/>{t('receiptIntelligence.reconciliationTitle')}</strong><p>{t(`receiptIntelligence.reconciliation.${status}`,{defaultValue:status})}{reconciliation.item_sum?` · ${t('receiptIntelligence.itemSum')}: ${money(reconciliation.item_sum,currency,i18n.language)}`:''}</p></div>
  {items.length>0&&<details><summary><span>{t('receiptIntelligence.lineItems')}</span><span>{t('receiptIntelligence.itemsCount',{count:items.length})}</span></summary><p>{t('receiptIntelligence.lineItemsHint')}</p><div className="receipt-line-items">{items.map((item,index)=><div className="receipt-line-item" key={`${item.line_index??index}-${item.description}`}><strong>{item.description}</strong><span>{money(item.total,currency,i18n.language)}</span><small>{item.quantity?`${t('receiptIntelligence.quantity')}: ${item.quantity}`:''}{item.quantity&&item.unit_price?' · ':''}{item.unit_price?`${t('receiptIntelligence.unitPrice')}: ${money(item.unit_price,currency,i18n.language)}`:''}{percent(item.semantic_confidence)!==null?` · ${t('receiptIntelligence.confidence')}: ${percent(item.semantic_confidence)}%`:''}</small></div>)}</div></details>}
  <details><summary>{t('receiptIntelligence.evidence')}</summary><p>{t('receiptIntelligence.evidenceHint')}</p>{evidence.length?<div className="receipt-evidence-list">{evidence.map(([key,entry])=><div className="receipt-evidence-row" key={key}><strong>{key}</strong>{entry.raw&&<span>{t('receiptIntelligence.raw')}: <code>{entry.raw}</code></span>}{entry.normalized!==null&&entry.normalized!==undefined&&entry.normalized!==''&&<span>{t('receiptIntelligence.normalized')}: <code>{String(entry.normalized)}</code></span>}{percent(entry.semantic_confidence)!==null&&<span>{t('receiptIntelligence.confidence')}: {percent(entry.semantic_confidence)}%</span>}</div>)}</div>:<p>{t('receiptIntelligence.noEvidence')}</p>}{candidates.length>1&&<><p><strong>{t('receiptIntelligence.totalCandidates')}</strong></p><div className="receipt-total-candidates">{candidates.slice(0,5).map((candidate,index)=><div className="receipt-total-candidate" key={`${candidate.amount}-${index}`}><strong>{money(candidate.amount,currency,i18n.language)}</strong><span>{candidate.line}</span><small>{t('receiptIntelligence.score')}: {candidate.score}</small></div>)}</div></>}</details>
 </section>;
}
