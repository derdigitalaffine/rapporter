import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import {requestCreate} from './create-request';
import './create-i18n';
import './today-quick-actions.css';

export default function TodayQuickActionsWidget({actions=[],suppressed=false}){
 const {t,i18n}=useTranslation();
 const de=i18n.language.startsWith('de');
 return <section className="today-section today-quick-actions" data-testid="today-quick-actions" aria-label={de?'Schnellaktionen':'Quick actions'}>
  <div className="today-section-head"><h2>{de?'Schnellaktionen':'Quick actions'}</h2></div>
  {actions.length?<div className="today-quick-actions-list">{actions.map(action=><button type="button" key={action.id} data-create-action={action.id} className="secondary" disabled={suppressed} onClick={()=>requestCreate(action.id,{source:'todayQuickActions'})}>
   <Icon name={action.icon}/><span><strong>{t(action.labelKey)}</strong><small>{t(`createUi.reason.${action.quickstart?.reason||'default'}`)}</small></span>
  </button>)}</div>:<p className="today-calm">{t('createUi.noActions')}</p>}
 </section>;
}
