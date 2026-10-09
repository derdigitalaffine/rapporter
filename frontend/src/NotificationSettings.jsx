import {useEffect,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';

function decodeKey(value){
 const padding='='.repeat((4-value.length%4)%4);const base64=(value+padding).replace(/-/g,'+').replace(/_/g,'/');const raw=atob(base64);return Uint8Array.from([...raw].map(c=>c.charCodeAt(0)));
}

export default function NotificationSettings({onBack,t}){
 const [config,setConfig]=useState(null);const [subscription,setSubscription]=useState(null);const [busy,setBusy]=useState(false);const [notice,setNotice]=useState('');
 async function load(){const cfg=await api('/push/config/');setConfig(cfg);if('serviceWorker'in navigator&&'PushManager'in window){const reg=await navigator.serviceWorker.ready;setSubscription(await reg.pushManager.getSubscription())}}
 useEffect(()=>{load().catch(e=>setNotice(e.message))},[]);
 async function enable(){setBusy(true);setNotice('');try{if(!config?.configured)throw new Error(t('pushNotConfigured'));if(Notification.permission==='denied')throw new Error(t('pushBlocked'));const permission=await Notification.requestPermission();if(permission!=='granted')throw new Error(t('pushPermissionRequired'));const reg=await navigator.serviceWorker.ready;let sub=await reg.pushManager.getSubscription();if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:decodeKey(config.public_key)});const json=sub.toJSON();await api('/push/subscribe/',{method:'POST',body:JSON.stringify(json)});setSubscription(sub);setNotice(t('pushEnabled'))}catch(e){setNotice(e.message)}finally{setBusy(false)}}
 async function disable(){if(!subscription)return;setBusy(true);setNotice('');try{const endpoint=subscription.endpoint;await api('/push/unsubscribe/',{method:'POST',body:JSON.stringify({endpoint})});await subscription.unsubscribe();setSubscription(null);setNotice(t('pushDisabled'))}catch(e){setNotice(e.message)}finally{setBusy(false)}}
 async function test(){setBusy(true);setNotice('');try{await api('/push/test/',{method:'POST',body:'{}'});setNotice(t('pushTestSent'))}catch(e){setNotice(e.message)}finally{setBusy(false)}}
 const supported='serviceWorker'in navigator&&'PushManager'in window&&'Notification'in window;
 return <div className="smart-page"><div className="page-head"><button className="back-button" onClick={onBack}><Icon name="back"/></button><h1 className="grow">{t('notifications')}</h1></div><p className="page-intro">{t('notificationsHint')}</p>{notice&&<div className="integration-notice">{notice}</div>}<section className="card notification-card"><div className="settings-hero-icon"><Icon name="warning" size={26}/></div><div className="grow"><strong>{subscription?t('pushActive'):t('pushInactive')}</strong><span>{!supported?t('pushUnsupported'):config?.configured?t('pushReady'):t('pushNotConfigured')}</span>{config?.devices>0&&<small>{t('registeredDevices',{count:config.devices})}</small>}</div></section><div className="action-row notification-actions">{supported&&!subscription&&<button className="primary" onClick={enable} disabled={busy||!config?.configured}><Icon name="warning"/>{t('enableNotifications')}</button>}{subscription&&<><button className="primary" onClick={test} disabled={busy}><Icon name="warning"/>{t('sendTest')}</button><button className="ghost-danger" onClick={disable} disabled={busy}><Icon name="close"/>{t('disableNotifications')}</button></>}</div><section className="card"><div className="row"><Icon name="automation"/><div className="grow"><strong>{t('pushRulesTitle')}</strong><span>{t('pushRulesHint')}</span></div></div></section></div>
}
