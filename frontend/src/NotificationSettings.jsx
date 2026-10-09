import {useEffect,useState} from 'react';
import './notification-i18n';
import './notification-settings.css';
import {api} from './api';
import {Icon} from './icons';
import {toast} from './feedback';

function decodeKey(value){
 const padding='='.repeat((4-value.length%4)%4);const base64=(value+padding).replace(/-/g,'+').replace(/_/g,'/');const raw=atob(base64);return Uint8Array.from([...raw].map(c=>c.charCodeAt(0)));
}

export default function NotificationSettings({onBack,onOpenAutomations,t}){
 const [config,setConfig]=useState(null);const [subscription,setSubscription]=useState(null);const [busy,setBusy]=useState(false);const [prepared,setPrepared]=useState(false);
 const supported='serviceWorker'in navigator&&'PushManager'in window&&'Notification'in window;
 const permission=supported?Notification.permission:'unsupported';
 async function load(){const cfg=await api('/push/config/');setConfig(cfg);if(supported){const reg=await navigator.serviceWorker.ready;setSubscription(await reg.pushManager.getSubscription())}}
 useEffect(()=>{load().catch(e=>toast(e.message||t('saveFailed'),{type:'error'}))},[]);
 async function enable(){setBusy(true);try{if(!config?.configured)throw new Error(t('pushNotConfigured'));if(Notification.permission==='denied')throw new Error(t('pushBlocked'));let granted=Notification.permission==='granted';if(!granted){const result=await Notification.requestPermission();granted=result==='granted';if(!granted){setPrepared(false);toast(t('pushUx.permissionDismissed'),{type:'warning'});return}}const reg=await navigator.serviceWorker.ready;let sub=await reg.pushManager.getSubscription();if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:decodeKey(config.public_key)});await api('/push/subscribe/',{method:'POST',body:JSON.stringify(sub.toJSON())});setSubscription(sub);setPrepared(false);const cfg=await api('/push/config/');setConfig(cfg);toast(t('pushEnabled'),{type:'success'})}catch(e){toast(e.message||t('pushUx.enableFailed'),{type:'error'})}finally{setBusy(false)}}
 async function disable(){if(!subscription)return;setBusy(true);try{const endpoint=subscription.endpoint;await api('/push/unsubscribe/',{method:'POST',body:JSON.stringify({endpoint})});await subscription.unsubscribe();setSubscription(null);const cfg=await api('/push/config/');setConfig(cfg);toast(t('pushDisabled'),{type:'success'})}catch(e){toast(e.message||t('pushUx.disableFailed'),{type:'error'})}finally{setBusy(false)}}
 async function test(){setBusy(true);try{await api('/push/test/',{method:'POST',body:'{}'});toast(t('pushTestSent'),{type:'success'})}catch(e){toast(e.message||t('pushUx.testFailed'),{type:'error'})}finally{setBusy(false)}}
 return <div className="smart-page"><div className="page-head"><button className="back-button" onClick={onBack} aria-label={t('back')}><Icon name="back"/></button><h1 className="grow">{t('notifications')}</h1></div><p className="page-intro">{t('notificationsHint')}</p>
 <div className="notification-state">
  {!supported&&<section className="card notification-card warning"><div className="settings-hero-icon"><Icon name="warning" size={24}/></div><div className="grow"><strong>{t('pushUx.unsupportedTitle')}</strong><span>{t('pushUx.unsupportedText')}</span></div></section>}
  {supported&&config&&!config.configured&&<section className="card notification-card warning"><div className="settings-hero-icon"><Icon name="settings" size={24}/></div><div className="grow"><strong>{t('pushUx.serverMissingTitle')}</strong><span>{t('pushUx.serverMissingText')}</span></div></section>}
  {supported&&config?.configured&&!subscription&&permission==='denied'&&<section className="card notification-card blocked"><div className="settings-hero-icon"><Icon name="warning" size={24}/></div><div className="grow"><strong>{t('pushUx.blockedTitle')}</strong><span>{t('pushUx.blockedText')}</span><div className="push-browser-help">{t('pushUx.blockedSteps')}</div><div className="push-actions"><button className="secondary" onClick={()=>window.location.reload()}><Icon name="refresh"/> {t('pushUx.reload')}</button></div></div></section>}
  {supported&&config?.configured&&!subscription&&permission!=='denied'&&!prepared&&<section className="card notification-card permission-stage"><div className="settings-hero-icon"><Icon name="warning" size={24}/></div><div className="grow"><strong>{t('pushUx.introTitle')}</strong><span>{t('pushUx.introText')}</span><ul className="push-benefits"><li><Icon name="check"/>{t('pushUx.benefitRules')}</li><li><Icon name="check"/>{t('pushUx.benefitDevice')}</li><li><Icon name="check"/>{t('pushUx.benefitPrivacy')}</li></ul><div className="push-actions"><button className="primary" onClick={()=>setPrepared(true)}><Icon name="next"/> {t('pushUx.continue')}</button></div></div></section>}
  {supported&&config?.configured&&!subscription&&permission!=='denied'&&prepared&&<section className="card notification-card permission-stage"><div className="settings-hero-icon"><Icon name="warning" size={24}/></div><div className="grow"><strong>{t('pushUx.permissionTitle')}</strong><span>{t('pushUx.permissionText')}</span><div className="push-actions"><button className="primary" onClick={enable} disabled={busy}><Icon name="warning"/> {t('pushUx.requestPermission')}</button><button className="secondary" onClick={()=>setPrepared(false)} disabled={busy}>{t('pushUx.notNow')}</button></div></div></section>}
  {subscription&&<section className="card notification-card"><div className="settings-hero-icon"><Icon name="check" size={24}/></div><div className="grow"><strong>{t('pushUx.activeTitle')}</strong><span>{t('pushUx.activeText')}</span>{config?.devices>0&&<span className="push-device-count">{t('pushUx.devicesContext',{count:config.devices})}</span>}<span>{t('pushUx.testHint')}</span><div className="push-actions"><button className="primary" onClick={test} disabled={busy}><Icon name="warning"/> {t('sendTest')}</button><button className="ghost-danger" onClick={disable} disabled={busy}><Icon name="close"/> {t('disableNotifications')}</button></div></div></section>}
 </div>
 <section className="card push-privacy"><Icon name="info"/><div><strong>{t('pushUx.privacyTitle')}</strong><span>{t('pushUx.privacyText')}</span></div></section>
 <section className="card push-rules-card"><Icon name="automation"/><div className="grow"><strong>{t('pushRulesTitle')}</strong><span>{t('pushUx.rulesCtaHint')}</span></div><button className="primary compact" onClick={onOpenAutomations}><Icon name="automation"/> {t('pushUx.rulesCta')}</button></section>
 </div>
}
