import {useEffect,useId,useMemo,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import {Icon} from './icons';
import {FormField,FormRow} from './form-primitives';
import {appLocale} from './locale';
import './statistics-i18n';
import './statistics.css';
import StatisticsAccessState from './StatisticsAccessState';
import {featureAvailability} from './feature-registry';

const RANGES=['7d','30d','90d','365d'];
const VIEWS=['overview','contributions','tasks','routines','shopping'];
const DOMAIN={tasks:'task',routines:'routine',shopping:'shopping'};
const COLORS={task:'var(--color-brand)',routine:'var(--color-positive)',shopping:'var(--color-info)'};
function readFilters(){const p=new URLSearchParams(location.search);return {range:RANGES.includes(p.get('stats_range'))?p.get('stats_range'):'30d',view:VIEWS.includes(p.get('stats_view'))?p.get('stats_view'):'overview',member:p.get('stats_member')||'',domain:p.get('stats_domain')||'',from:p.get('stats_from')||'',to:p.get('stats_to')||''}}
function filtersHref(filters){const url=new URL(location.href);for(const [key,value] of Object.entries(filters)){const param=`stats_${key}`;if(value)url.searchParams.set(param,value);else url.searchParams.delete(param)}return `${url.pathname}${url.search}${url.hash}`}
function queryFor(family,filters){const p=new URLSearchParams({family:String(family.id),range:filters.range});for(const key of ['member','domain','from','to'])if(filters[key])p.set(key,filters[key]);return p.toString()}
function safeCsv(value){const text=String(value??'');return `"${(/^[=+@\-\t\r]/.test(text)?"'":"")+text.replaceAll('"','""')}"`}

export default function StatisticsHub({family,entitlements,role,onBack}){
 const {t}=useTranslation();
 const availability=family?featureAvailability('statistics',{entitlements,role}):'pending';
 if(availability!=='available')return <StatisticsAccessState kind={availability} onBack={onBack}/>;
 return <StatisticsContent key={family.id} family={family} onBack={onBack}/>;
}

function StatisticsContent({family,onBack}){
 const {t,i18n}=useTranslation();
 const locale=appLocale(i18n.language);
 const number=value=>new Intl.NumberFormat(locale,{maximumFractionDigits:1}).format(value??0);
 const date=value=>value?new Intl.DateTimeFormat(locale,{day:'numeric',month:'short',year:'numeric',timeZone:/^\d{4}-\d{2}-\d{2}$/.test(value)?'UTC':family.timezone}).format(new Date(value)):t('statisticsUi.unavailable');
 const dateTime=value=>value?new Intl.DateTimeFormat(locale,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',timeZone:family.timezone}).format(new Date(value)):'';
 const [filters,setFilters]=useState(readFilters);
 const [data,setData]=useState(null);
 const [loading,setLoading]=useState(true);
 const [error,setError]=useState('');
 const [stale,setStale]=useState(false);
 const [retry,setRetry]=useState(0);
 const [page,setPage]=useState(1);
 const [detail,setDetail]=useState(null);
 const [detailError,setDetailError]=useState('');
 const [detailLoading,setDetailLoading]=useState(false);
 const [table,setTable]=useState(false);
 const [metric,setMetric]=useState('count');
 const [custom,setCustom]=useState(()=>Boolean(filters.from&&filters.to));
 const [dates,setDates]=useState({from:filters.from,to:filters.to});
 const [rangeError,setRangeError]=useState('');
 const revision=useRef(0);
 const detailRevision=useRef(0);
 const snapshot=useRef(null);
 const query=queryFor(family,filters);
 const detailKey=DOMAIN[filters.view];
 const titleId=useId();
 function change(next){const value={...filters,...next};history.pushState({...history.state,statistics:true},'',filtersHref(value));setFilters(value);setPage(1);setTable(false)}
 function changeView(view){change({view,domain:DOMAIN[view]||filters.domain})}
 useEffect(()=>{const listener=()=>{setFilters(readFilters());setPage(1);setTable(false)};window.addEventListener('popstate',listener);return()=>window.removeEventListener('popstate',listener)},[]);
 useEffect(()=>{
  const id=++revision.current;const controller=new AbortController();
  setLoading(true);setError('');setStale(false);
  // Never show another range/member's snapshot during a request.
  const same=snapshot.current?.query===query;
  setData(same?snapshot.current.data:null);
  api(`/statistics/?${query}`,{signal:controller.signal}).then(value=>{if(id!==revision.current)return;snapshot.current={query,data:value};setData(value)}).catch(err=>{
   if(id!==revision.current||err.name==='AbortError')return;
   if([401,403,404].includes(err.status)||err.message==='unauthorized'){snapshot.current=null;setData(null);setError(t('statisticsUi.denied'));return}
   if(same){setData(snapshot.current.data);setStale(true)}
   setError(t('statisticsUi.loadError'));
  }).finally(()=>{if(id===revision.current)setLoading(false)});
  return()=>{revision.current++;controller.abort()};
 },[query,retry,t]);
 useEffect(()=>{
  const id=++detailRevision.current;const controller=new AbortController();setDetail(null);setDetailError('');
  if(!detailKey){setDetailLoading(false);return()=>controller.abort()}
  setDetailLoading(true);
  api(`/statistics/${filters.view}/?${query}&page=${page}`,{signal:controller.signal}).then(value=>{if(id===detailRevision.current)setDetail(value)}).catch(err=>{if(id===detailRevision.current&&err.name!=='AbortError')setDetailError(t('statisticsUi.detailError'))}).finally(()=>{if(id===detailRevision.current)setDetailLoading(false)});
  return()=>{detailRevision.current++;controller.abort()};
 },[detailKey,filters.view,query,page,retry,t]);
 useEffect(()=>{const online=()=>setRetry(n=>n+1);const offline=()=>{if(snapshot.current?.query===query)setStale(true)};window.addEventListener('online',online);window.addEventListener('offline',offline);return()=>{window.removeEventListener('online',online);window.removeEventListener('offline',offline)}},[query]);
 function applyDates(event){event.preventDefault();const a=new Date(`${dates.from}T00:00:00Z`),b=new Date(`${dates.to}T00:00:00Z`);if(!dates.from||!dates.to||!Number.isFinite(+a)||!Number.isFinite(+b)||b<a||(b-a)/86400000>=365){setRangeError(t('statisticsUi.invalidRange'));return}setRangeError('');change({...dates})}
 function exportData(){if(!data?.meta.can_export||stale)return;const columns=['date','completed','organized','task_completions','effort_minutes','effort_coverage'];const text='\uFEFF'+[columns,...data.timeseries.map(row=>columns.map(key=>row[key]))].map(row=>row.map(safeCsv).join(',')).join('\r\n');const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`family-statistics-${data.meta.from}-${data.meta.to}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
 const domains=data?.domains||[];
 const summary=data?.summary;
 const domainName=key=>t(`statisticsUi.${key}`);
 const trend=useMemo(()=>{const series=data?.timeseries||[];const step=series.length>90?30:series.length>14?7:1;const rows=[];for(let i=0;i<series.length;i+=step){const group=series.slice(i,i+step);rows.push({date:group[0].date,end:group.at(-1).date,completed:group.reduce((sum,row)=>sum+row.completed,0),organized:group.reduce((sum,row)=>sum+row.organized,0)})}return rows},[data]);
 const members=data?.members||[];
 const canEffort=(summary?.effort_coverage||0)>=50;
 const maxMember=Math.max(1,...members.map(row=>metric==='effort'?row.effort_minutes:row.completed+row.organized));
 const maxTrend=Math.max(1,...trend.flatMap(row=>[row.completed,row.organized]));
 const showMembers=['overview','contributions'].includes(filters.view);
 const canSeeDomain=key=>data?.meta.available_domains.includes(key);
 const completedDomain=key=>domains.find(row=>row.key===key)?.completed||0;
 return <div className="statistics-page" aria-labelledby={titleId}>
  <header className="statistics-header"><div><button className="ghost statistics-back" onClick={onBack}><Icon name="back"/>{t('statisticsUi.back')}</button><small>{family.name} · Premium</small><h1 id={titleId}>{t('statisticsUi.title')}</h1><p>{t('statisticsUi.subtitle')}</p></div><button className="secondary" onClick={()=>setRetry(n=>n+1)} disabled={loading}><Icon name="refresh"/>{t('statisticsUi.refresh')}</button></header>
  <section className="card statistics-controls" aria-label={t('statisticsUi.filters')}>
   <div className="statistics-period" role="group" aria-label={t('statisticsUi.period')}>{RANGES.map(range=><button className="secondary" aria-pressed={!filters.from&&filters.range===range} key={range} onClick={()=>{setCustom(false);change({range,from:'',to:''})}}>{t(`statisticsUi.range_${range}`)}</button>)}<button className="ghost" aria-expanded={custom} onClick={()=>setCustom(!custom)}>{t('statisticsUi.custom')}</button></div>
   {custom&&<form className="statistics-custom" onSubmit={applyDates}><FormRow><FormField label={t('statisticsUi.from')}><input type="date" value={dates.from} onChange={e=>setDates({...dates,from:e.target.value})} required/></FormField><FormField label={t('statisticsUi.to')}><input type="date" value={dates.to} onChange={e=>setDates({...dates,to:e.target.value})} required/></FormField></FormRow><button className="primary" type="submit">{t('statisticsUi.apply')}</button>{rangeError&&<p role="alert">{rangeError}</p>}</form>}
   <details className="statistics-filter-details"><summary>{t('statisticsUi.filters')}{(filters.member||filters.domain)&&<span>{t('statisticsUi.activeFilters')}</span>}</summary><div className="statistics-filter-body"><FormRow><FormField label={t('statisticsUi.member')}><select value={filters.member} onChange={e=>change({member:e.target.value})}><option value="">{data?.meta.scope==='self'?t('statisticsUi.myProgress'):t('statisticsUi.allMembers')}</option>{members.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></FormField><FormField label={t('statisticsUi.domain')}><select value={filters.domain} onChange={e=>change({domain:e.target.value})}><option value="">{t('statisticsUi.allDomains')}</option>{(data?.meta.available_domains||['task','routine','shopping']).map(key=><option key={key} value={key}>{domainName(key)}</option>)}</select></FormField></FormRow><button className="ghost" onClick={()=>change({member:'',domain:''})}>{t('statisticsUi.reset')}</button></div></details>
  </section>
  <nav className="statistics-nav" aria-label={t('statisticsUi.sections')}>{VIEWS.filter(view=>!DOMAIN[view]||!data||canSeeDomain(DOMAIN[view])).map(view=><button className="ghost" aria-current={filters.view===view?'page':undefined} key={view} onClick={()=>changeView(view)}>{t(`statisticsUi.${view}`)}</button>)}</nav>
  <div className="statistics-view-picker"><FormField label={t('statisticsUi.sections')}><select value={filters.view} onChange={e=>changeView(e.target.value)}>{VIEWS.filter(view=>!DOMAIN[view]||!data||canSeeDomain(DOMAIN[view])).map(view=><option key={view} value={view}>{t(`statisticsUi.${view}`)}</option>)}</select></FormField></div>
  {loading&&<p className="statistics-loading" role="status">{t('statisticsUi.loading')}</p>}
  {error&&<section className="card statistics-state" role="alert"><p>{error}</p><button className="secondary" onClick={()=>setRetry(n=>n+1)}>{t('statisticsUi.retry')}</button></section>}
  {data&&<>
   <p className="statistics-snapshot" role="status">{date(data.meta.from)} – {date(data.meta.to)} · {data.meta.timezone}{stale&&<strong>{t('statisticsUi.stale',{date:dateTime(data.meta.generated_at)})}</strong>}</p>
   {!summary.completed&&!summary.organized&&<section className="card statistics-state"><Icon name="progress"/><h2>{t('statisticsUi.emptyTitle')}</h2><p>{t('statisticsUi.empty')}</p></section>}
   {['overview','contributions'].includes(filters.view)&&<div className="statistics-kpis">
    <Metric label={t('statisticsUi.completed')} value={number(summary.completed)} icon="check" hint={t('statisticsUi.activityMix')}/>
    <Metric label={t('statisticsUi.organized')} value={number(summary.organized)} icon="calendar" hint={t('statisticsUi.planningHint')}/>
    {canSeeDomain('routine')&&<Metric label={domainName('routine')} value={number(completedDomain('routine'))} icon="history" hint={t('statisticsUi.executionHint')}/>}
    {canSeeDomain('shopping')&&<Metric label={domainName('shopping')} value={number(completedDomain('shopping'))} icon="shopping" hint={t('statisticsUi.purchaseHint')}/>}
   </div>}
   {data.meta.scope==='self'&&<p className="statistics-privacy-note">{t('statisticsUi.myProgressHint')}</p>}
   {!data.meta.can_compare_members&&data.meta.scope!=='self'&&<p className="statistics-privacy-note">{t('statisticsUi.teenHint')}</p>}
   <div className="statistics-layout">
    {showMembers&&<section className="card statistics-distribution" aria-labelledby="statistics-members-title"><div className="statistics-section-head"><div><h2 id="statistics-members-title">{t('statisticsUi.distribution')}</h2><p>{t('statisticsUi.neutralOrder')}</p></div><button className="ghost" aria-pressed={table} onClick={()=>setTable(!table)}>{t(table?'statisticsUi.asChart':'statisticsUi.asTable')}</button></div>
     {canEffort&&<div role="group" className="statistics-metric" aria-label={t('statisticsUi.measure')}><button className="secondary" aria-pressed={metric==='count'} onClick={()=>setMetric('count')}>{t('statisticsUi.count')}</button><button className="secondary" aria-pressed={metric==='effort'} onClick={()=>setMetric('effort')}>{t('statisticsUi.estimated')}</button></div>}
     {table?<DataTable caption={t('statisticsUi.distribution')} columns={[t('statisticsUi.member'),t('statisticsUi.completed'),t('statisticsUi.organized'),domainName('task'),domainName('routine'),domainName('shopping'),t('statisticsUi.estimated')]} rows={members.map(row=>[row.name,number(row.completed),number(row.organized),number(row.domains.find(d=>d.key==='task')?.completed||0),number(row.domains.find(d=>d.key==='routine')?.completed||0),number(row.domains.find(d=>d.key==='shopping')?.completed||0),`${number(row.effort_minutes)} ${t('statisticsUi.minutes')} · ${row.effort_coverage===null?'—':number(row.effort_coverage)+' %'}`])}/>:<div className="statistics-member-bars">{members.map(row=><div className="statistics-member" key={row.id}><div className="statistics-member-head"><button className="ghost" onClick={()=>change({member:row.id,view:'contributions'})}>{row.name}{row.self&&<small>{t('statisticsUi.you')}</small>}</button><strong>{number(metric==='effort'?row.effort_minutes:row.completed+row.organized)}{metric==='effort'&&` ${t('statisticsUi.minutes')}`}</strong></div><div className="statistics-bar-track" aria-hidden="true">{metric==='effort'?<span style={{width:`${row.effort_minutes/maxMember*100}%`,background:COLORS.task}}/>:<>{row.domains.map(d=><span key={d.key} style={{width:`${d.completed/maxMember*100}%`,background:COLORS[d.key]}}/>)}<span className="statistics-plan-segment" style={{width:`${row.organized/maxMember*100}%`}}/></>}</div><p>{metric==='effort'?t('statisticsUi.effortCoverage',{minutes:number(row.effort_minutes),coverage:row.effort_coverage===null?'—':number(row.effort_coverage)}):<>{row.domains.filter(d=>d.completed).map(d=>`${domainName(d.key)} ${number(d.completed)}`).join(' · ')||t('statisticsUi.noExecution')} · {t('statisticsUi.organized')} {number(row.organized)}</>}</p></div>)}</div>}
     {summary.completed-summary.attributed>0&&<p className="statistics-quality-note">{t('statisticsUi.unknownActor',{count:number(summary.completed-summary.attributed)})}</p>}
    </section>}
    <section className="card statistics-domains" aria-labelledby="statistics-domain-title"><h2 id="statistics-domain-title">{t('statisticsUi.byDomain')}</h2><p>{t('statisticsUi.domainHint')}</p>{domains.map(row=><button className="statistics-domain-row ghost" key={row.key} onClick={()=>changeView({task:'tasks',routine:'routines',shopping:'shopping'}[row.key])}><span><Icon name={{task:'tasks',routine:'history',shopping:'shopping'}[row.key]}/><strong>{domainName(row.key)}</strong></span><span><b>{number(row.completed)}</b> {t('statisticsUi.completed')}<small>{number(row.organized)} {t('statisticsUi.organized')}</small></span><Icon name="next"/></button>)}{canSeeDomain('task')&&<p className="statistics-quality-note">{t('statisticsUi.overdueNow',{count:number(summary.overdue_now)})}</p>}{canEffort&&<p>{t('statisticsUi.effortCoverage',{minutes:number(summary.effort_minutes),coverage:number(summary.effort_coverage)})}</p>}</section>
    <section className="card statistics-trend" aria-labelledby="statistics-trend-title"><div className="statistics-section-head"><div><h2 id="statistics-trend-title">{t('statisticsUi.trend')}</h2><p>{t('statisticsUi.trendHint')}</p></div><TrendTableToggle rows={trend} number={number} date={date} t={t} max={maxTrend}/></div></section>
   </div>
   {detailKey&&<section className="card statistics-detail" aria-labelledby="statistics-detail-title"><h2 id="statistics-detail-title">{t(`statisticsUi.${filters.view}`)}</h2><p>{t('statisticsUi.detailHint')}</p>{detailLoading&&<p role="status">{t('statisticsUi.loading')}</p>}{detailError&&<div role="alert"><p>{detailError}</p><button className="secondary" onClick={()=>setRetry(n=>n+1)}>{t('statisticsUi.retry')}</button></div>}{detail&&<>
    {detailKey==='routine'&&<><p className="statistics-quality-note">{t('statisticsUi.dueUnavailable')}</p><p>{t('statisticsUi.activeRoutines',{count:number(detail.active_routines)})}</p><div className="statistics-routine-list">{detail.routines?.map(row=><a className="statistics-routine-row" key={row.id} href={row.href}><span><strong>{row.name}</strong><small>{row.interval_days?t('statisticsUi.interval',{days:row.interval_days}):t('statisticsUi.adaptive')}</small>{row.next_due&&<small>{t('statisticsUi.nextDue',{date:dateTime(row.next_due)})}</small>}</span><b>{number(row.completed)} {t('statisticsUi.completed')}</b><Icon name="next"/></a>)}</div></>}
    {!detail.count?<p>{t('statisticsUi.emptyDetail')}</p>:<DataTable caption={t('statisticsUi.history')} columns={[t('statisticsUi.date'),t('statisticsUi.action'),t('statisticsUi.member'),t('statisticsUi.estimated'),t('statisticsUi.open')]} rows={detail.results.map(row=>[dateTime(row.occurred_at),t(`statisticsUi.action_${row.action}`),members.find(m=>m.id===row.member)?.name||t('statisticsUi.notAttributed'),row.effort_minutes===null?'—':`${number(row.effort_minutes)} ${t('statisticsUi.minutes')}`,<a href={canonicalHref(row,family.id)} key={row.id}>{t('statisticsUi.openDomain',{domain:domainName(detailKey)})}</a>])}/>}
    <div className="statistics-pagination"><button className="secondary" disabled={page===1} onClick={()=>setPage(n=>n-1)}>{t('statisticsUi.previous')}</button><span>{t('statisticsUi.page',{page})}</span><button className="secondary" disabled={!detail.has_next} onClick={()=>setPage(n=>n+1)}>{t('statisticsUi.next')}</button></div>
   </>}</section>}
   {filters.view==='overview'&&data.insights.length>0&&<section className="card statistics-insights"><h2>{t('statisticsUi.changed')}</h2><ul>{data.insights.map((insight,index)=><li key={index}><button className="ghost" onClick={()=>changeView(insight.domain?{task:'tasks',routine:'routines',shopping:'shopping'}[insight.domain]:'contributions')}>{t(`statisticsUi.insight_${insight.key}`,{value:number(insight.value)})}<Icon name="next"/></button></li>)}</ul></section>}
   <details className="card statistics-definitions"><summary>{t('statisticsUi.dataQuality')}</summary><div><p>{t('statisticsUi.coverage',{value:data.meta.actor_coverage===null?'—':number(data.meta.actor_coverage)})}</p><p>{t('statisticsUi.historical',{date:date(data.meta.attribution_since||data.meta.generated_at)})}</p><p>{t('statisticsUi.definitions')}</p><p>{t('statisticsUi.dueUnavailable')}</p><p>{t('statisticsUi.privacy')}</p></div></details>
   <footer className="statistics-footer"><span>{t('statisticsUi.updated',{date:dateTime(data.meta.generated_at)})}</span>{data.meta.can_export&&<button className="ghost" disabled={stale||loading} onClick={exportData}><Icon name="download"/>{t('statisticsUi.export')}</button>}</footer>
  </>}
 </div>;
}

function Metric({label,value,icon,hint}){return <section className="card statistics-kpi"><span><Icon name={icon}/>{label}</span><strong>{value}</strong><p>{hint}</p></section>}
function DataTable({caption,columns,rows}){return <table className="statistics-table"><caption className="sr-only">{caption}</caption><thead><tr>{columns.map((label,index)=><th key={index} scope="col">{label}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{row.map((cell,col)=><td data-label={columns[col]} key={col}>{cell}</td>)}</tr>)}</tbody></table>}
function canonicalHref(row,family){const p=new URLSearchParams({page:row.page,family:String(family)});if(row.entity&&row.page!=='shopping')p.set(row.page==='tasks'?'task':'routine',row.entity);return `?${p}`}
function TrendTableToggle({rows,number,date,t,max}){
 const [table,setTable]=useState(false);
 const id=useId();
 return <div className="statistics-trend-body"><button className="ghost" aria-pressed={table} onClick={()=>setTable(!table)}>{t(table?'statisticsUi.asChart':'statisticsUi.asTable')}</button>{table?<DataTable caption={t('statisticsUi.trend')} columns={[t('statisticsUi.period'),t('statisticsUi.completed'),t('statisticsUi.organized')]} rows={rows.map(row=>[`${date(row.date)}${row.end!==row.date?' – '+date(row.end):''}`,number(row.completed),number(row.organized)])}/>:<><p id={id} className="sr-only">{t('statisticsUi.chartSummary',{completed:number(rows.reduce((sum,row)=>sum+row.completed,0)),organized:number(rows.reduce((sum,row)=>sum+row.organized,0))})}</p><div className="statistics-trend-bars" role="img" aria-labelledby={id}>{rows.map(row=><div key={row.date} className="statistics-trend-bar"><div aria-hidden="true"><span style={{height:`${row.completed/max*100}%`}}/><span style={{height:`${row.organized/max*100}%`}}/></div><b>{number(row.completed)} / {number(row.organized)}</b><small>{date(row.date)}</small></div>)}</div><p className="statistics-trend-legend">{t('statisticsUi.completed')} / {t('statisticsUi.organized')}</p></>}</div>;
}
