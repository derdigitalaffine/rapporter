import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import './statistics-i18n';
import './statistics.css';

// Shared by the lightweight route gate and the hub, without loading report code.
export default function StatisticsAccessState({kind,onBack}){
  const {t}=useTranslation();
  if(kind==='pending')return <p role="status">{t('pleaseWait')}</p>;
  if(kind==='denied')return <section className="card statistics-state"><Icon name="lock"/><h1>{t('statisticsUi.title')}</h1><p>{t('statisticsUi.guest')}</p><button className="secondary" onClick={onBack}>{t('statisticsUi.back')}</button></section>;
  return <section className="card statistics-state"><span className="entitlement-tier">Premium</span><h1>{t('statisticsUi.title')}</h1><p>{t('statisticsUi.subtitle')}</p><p>{t('statisticsUi.locked')}</p><button className="primary" onClick={onBack}>{t('statisticsUi.access')}</button></section>;
}
