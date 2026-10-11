import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import ContractEditor from './ContractEditor';
import './contracts-i18n';
import './contracts.css';

export default function ContractsHub({family,onBack,onCreate}){
 const {t}=useTranslation();const [rows,setRows]=useState([]);const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [editing,setEditing]=useState(null);
 async function load(){if(!family?.id)return;setLoading(true);setError('');try{setRows(await api(`/contracts/?family=${encodeURIComponent(family.id)}`))}catch(err){setError(err.message||t('contractUi.loadFailed'))}finally{setLoading(false)}}
 useEffect(()=>{load()},[family?.id]);
 return <section className="contracts-page"><div className="contracts-head"><div className="page-head"><button className="icon-button" onClick={onBack} aria-label={t('contractUi.close')}><Icon name="back"/></button><h1>{t('contractUi.title')}</h1></div><button className="primary compact" onClick={()=>onCreate?.('contract')}><Icon name="plus"/>{t('contractUi.add')}</button></div>{loading&&<div className="smart-empty" role="status"><Icon name="refresh"/><span>{t('sessionUi.loading')}</span></div>}{error&&<div className="smart-empty" role="alert"><Icon name="warning"/><strong>{t('contractUi.loadFailed')}</strong><span>{error}</span><button className="secondary compact" onClick={load}>{t('contractUi.retry')}</button></div>}{!loading&&!error&&!rows.length&&<div className="smart-empty"><Icon name="receipt" size={34}/><strong>{t('contractUi.empty')}</strong><span>{t('contractUi.emptyHint')}</span></div>}<div className="contracts-list">{rows.map(contract=>{const deadline=contract.derived_dates?.find(item=>item.key==='cancellation_deadline');return <button type="button" className="card contract-card" key={contract.id} onClick={()=>setEditing(contract)}><span className="contract-card-main"><strong>{contract.title}</strong><span>{contract.provider||contract.category||'—'}</span><span className="contract-card-meta"><span>{t(`contractUi.${contract.status}`)}</span>{deadline&&<span>{t('contractUi.cancellationDeadline',{date:deadline.date})}</span>}</span></span><span className="contract-badge"><Icon name={contract.visibility==='private'?'lock':'members'} size={13}/>{t(`contractUi.${contract.visibility==='private'?'private':'family'}`)}</span></button>})}</div>{editing&&<ContractEditor family={family} contract={editing} onClose={()=>setEditing(null)} onSaved={async()=>{setEditing(null);await load()}}/>}</section>
}
