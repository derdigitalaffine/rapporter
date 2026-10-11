import React,{useEffect,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import './documents-i18n';
import './documents.css';

const EMPTY_FILTERS={kind:'',person:'',visibility:'',date_from:'',date_to:'',correspondent:'',pinned:''};

export default function DocumentsHub({family,onBack}){
 const {t,i18n}=useTranslation('documents');
 const [query,setQuery]=useState('');
 const [filters,setFilters]=useState(EMPTY_FILTERS);
 const [advanced,setAdvanced]=useState(false);
 const [rows,setRows]=useState([]);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const members=family?.memberships||[];
 const filterKey=useMemo(()=>JSON.stringify(filters),[filters]);
 const activeFilterCount=Object.values(filters).filter(Boolean).length;

 useEffect(()=>{
  let cancelled=false;
  const timer=setTimeout(async()=>{
   if(!family?.id)return;
   setLoading(true);setError('');
   const params=new URLSearchParams({family:String(family.id)});
   if(query.trim())params.set('q',query.trim());
   Object.entries(filters).forEach(([key,value])=>{if(value)params.set(key,value)});
   try{
    const data=await api(`/documents/search/?${params.toString()}`);
    if(!cancelled)setRows(data.results||[]);
   }catch(err){if(!cancelled)setError(err.message||t('loadFailed'))}
   finally{if(!cancelled)setLoading(false)}
  },250);
  return()=>{cancelled=true;clearTimeout(timer)};
 },[family?.id,query,filterKey,t]);

 const setFilter=(key,value)=>setFilters(current=>({...current,[key]:value}));
 const resetFilters=()=>setFilters(EMPTY_FILTERS);
 const locale=i18n.language?.startsWith('en')?'en-US':'de-DE';
 const formatDate=value=>value?new Intl.DateTimeFormat(locale,{dateStyle:'medium'}).format(new Date(`${value}T12:00:00`)):'';

 return <section className="documents-hub">
  <header className="documents-header">
   <button className="icon-button" type="button" onClick={onBack} aria-label={t('back')}><Icon name="back"/></button>
   <div className="grow"><small>{family?.name||''}</small><h1>{t('title')}</h1></div>
  </header>

  <section className="documents-search-panel" aria-label={t('searchRegion')}>
   <label className="documents-search-field">
    <span className="sr-only">{t('search')}</span>
    <Icon name="search"/>
    <input type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder={t('searchPlaceholder')} autoComplete="off"/>
   </label>
   <button className={`secondary documents-filter-toggle ${activeFilterCount?'active':''}`} type="button" aria-expanded={advanced} onClick={()=>setAdvanced(value=>!value)}>
    <Icon name="filter"/>{t('filters')}{activeFilterCount?<span className="documents-filter-count" aria-label={t('activeFilters',{count:activeFilterCount})}>{activeFilterCount}</span>:null}
   </button>

   {advanced&&<div className="documents-filters">
    <label>{t('type')}<input value={filters.kind} onChange={event=>setFilter('kind',event.target.value)} placeholder={t('typePlaceholder')}/></label>
    <label>{t('person')}<select value={filters.person} onChange={event=>setFilter('person',event.target.value)}><option value="">{t('all')}</option>{members.map(member=><option value={member.id} key={member.id}>{member.display_name||member.username||member.user}</option>)}</select></label>
    <label>{t('visibility')}<select value={filters.visibility} onChange={event=>setFilter('visibility',event.target.value)}><option value="">{t('all')}</option><option value="private">{t('private')}</option><option value="family">{t('family')}</option><option value="selected">{t('selected')}</option><option value="shared">{t('shared')}</option></select></label>
    <label>{t('correspondent')}<input value={filters.correspondent} onChange={event=>setFilter('correspondent',event.target.value)} placeholder={t('correspondentPlaceholder')}/></label>
    <label>{t('dateFrom')}<input type="date" value={filters.date_from} onChange={event=>setFilter('date_from',event.target.value)}/></label>
    <label>{t('dateTo')}<input type="date" value={filters.date_to} onChange={event=>setFilter('date_to',event.target.value)}/></label>
    <label>{t('pinned')}<select value={filters.pinned} onChange={event=>setFilter('pinned',event.target.value)}><option value="">{t('all')}</option><option value="true">{t('yes')}</option><option value="false">{t('no')}</option></select></label>
    <div className="documents-filter-actions"><button className="text-button" type="button" onClick={resetFilters} disabled={!activeFilterCount}>{t('reset')}</button></div>
   </div>}
  </section>

  <div className="documents-result-head" aria-live="polite">
   <strong>{loading?t('loading'):t('resultCount',{count:rows.length})}</strong>
   {query.trim()&&<span>{t('forQuery',{query:query.trim()})}</span>}
  </div>
  {error&&<div className="documents-alert" role="alert"><Icon name="warning"/><span>{t('loadFailed')}</span><button className="text-button" type="button" onClick={()=>setQuery(value=>`${value} `)}>{t('retry')}</button></div>}
  {!loading&&!error&&rows.length===0&&<div className="smart-empty documents-empty"><Icon name="search" size={32}/><strong>{t('empty')}</strong><span>{t('emptyHint')}</span></div>}
  <div className="documents-results">
   {rows.map(row=><article className="documents-result-card" key={row.id}>
    <div className="documents-result-main">
     <div className="documents-result-title"><Icon name={row.pinned?'favorite':'receipt'}/><strong>{row.title||t('untitled')}</strong></div>
     <div className="documents-result-meta">
      {row.document_date&&<span>{formatDate(row.document_date)}</span>}
      {row.correspondent&&<span>{row.correspondent}</span>}
      {row.kind&&<span>{row.kind}</span>}
      <span>{t(`visibility_${row.visibility}`,{defaultValue:row.visibility})}</span>
     </div>
     {row.snippet&&<p className="documents-snippet">{row.snippet}</p>}
    </div>
    <a className="secondary compact documents-open" href={row.file_url} target="_blank" rel="noreferrer"><span>{t('open')}</span><Icon name="next"/></a>
   </article>)}
  </div>
 </section>
}
