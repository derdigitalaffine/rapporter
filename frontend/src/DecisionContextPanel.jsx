import {useId,useMemo,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import {useFamilyPermissions} from './family-permissions';
import {decisionContextHref,decisionPresetsFor} from './decision-context';
import './decision-context-panel.css';

export default function DecisionContextPanel({family,context}){
 const {i18n}=useTranslation();
 const en=i18n.language.startsWith('en');
 const {role}=useFamilyPermissions(family);
 const canCreate=Boolean(role&&role!=='guest');
 const presets=useMemo(()=>decisionPresetsFor(context?.type,en),[context?.type,en]);
 const w=en?{
  action:'Vote together',title:'Decide together',hint:'Choose a starting point. The decision itself is created and managed in Decisions.',openAll:'Open Decisions'
 }:{
  action:'Gemeinsam abstimmen',title:'Gemeinsam entscheiden',hint:'Wähle einen Einstieg. Die Entscheidung selbst wird zentral unter Entscheidungen erstellt und verwaltet.',openAll:'Entscheidungen öffnen'
 };
 const [open,setOpen]=useState(false);
 const regionId=useId();
 const titleId=useId();
 if(!canCreate||!presets.length)return null;
 return <section className="decision-context-panel">
  <button type="button" className="secondary decision-context-toggle" onClick={()=>setOpen(value=>!value)} aria-expanded={open} aria-controls={regionId}><Icon name="check"/><span>{w.action}</span><span className="decision-context-toggle__indicator" aria-hidden="true">{open?'−':'+'}</span></button>
  {open&&<div id={regionId} className="decision-context-panel__body" role="region" aria-labelledby={titleId}>
   <header className="decision-context-panel__intro"><strong id={titleId}>{w.title}</strong><p>{w.hint}</p></header>
   <div className="decision-context-presets" role="group" aria-label={w.title}>{presets.map(item=><a className="secondary" key={item.key} href={decisionContextHref(context,item.key)}><Icon name="check"/>{item.label}</a>)}</div>
   <a className="text-button decision-context-open-all" href={decisionContextHref(null)}>{w.openAll}</a>
  </div>}
 </section>;
}
