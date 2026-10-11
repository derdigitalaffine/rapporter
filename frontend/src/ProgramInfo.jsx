import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import packageMeta from '../package.json';
import {Icon} from './icons';
import {loadFamilyOsReleaseManifest,releaseFeaturesForLanguage} from './familyos-release';
import './program-info-i18n';
import './program-info.css';

export default function ProgramInfo(){
 const {t,i18n}=useTranslation();
 const [manifest,setManifest]=useState(null);
 const [failed,setFailed]=useState(false);
 useEffect(()=>{let active=true;loadFamilyOsReleaseManifest().then(value=>{if(active){setManifest(value);setFailed(false)}}).catch(()=>{if(active)setFailed(true)});return()=>{active=false}},[]);
 const features=manifest?releaseFeaturesForLanguage(manifest,i18n.language):[];
 const releaseDate=manifest?new Intl.DateTimeFormat(i18n.language||'de',{dateStyle:'medium'}).format(new Date(`${manifest.released_at}T00:00:00Z`)):'';
 return <section className="card program-info" aria-labelledby="program-info-title">
  <div className="program-info-head"><div><small>{t('programInfoUi.familyOs')}</small><h2 id="program-info-title">{t('programInfoUi.title')}</h2></div><Icon name="info" size={22}/></div>
  <div className="program-info-version"><span>{t('programInfoUi.version')}</span><strong>{packageMeta.version}</strong></div>
  <div className="program-info-release"><h3>{t('programInfoUi.whatsNew')}</h3>{manifest&&<small>{t('programInfoUi.released',{date:releaseDate})}</small>}
   {!manifest&&!failed&&<p className="program-info-state" role="status">{t('programInfoUi.loading')}</p>}
   {failed&&<p className="program-info-state">{t('programInfoUi.unavailable')}</p>}
   {manifest&&<ul className="program-info-features">{features.map(feature=><li key={feature.id}><strong>{feature.title}</strong><span>{feature.description}</span></li>)}</ul>}
  </div>
 </section>;
}
