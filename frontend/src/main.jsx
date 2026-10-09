import React from 'react';
import ReactDOM from 'react-dom/client';
import '@fontsource-variable/nunito';
import './i18n';
import './styles.css';
import './sheets.css';
import './smart.css';
import './smart-extra.css';
import './automation-guided.css';
import './design-system.css';
import './feedback.css';
import './accessibility.css';
import './today-home.css';
import App from './App';
import InviteFlow from './InviteFlow';
import FeedbackHost from './feedback';
import AccessibilityManager from './AccessibilityManager';

class BootErrorBoundary extends React.Component {
  constructor(props){super(props);this.state={error:null}}
  static getDerivedStateFromError(error){return {error}}
  componentDidCatch(error,info){console.error('fam-uh-le frontend crash',error,info)}
  render(){
    if(!this.state.error)return this.props.children;
    return <main className="login-shell"><section className="card login-card"><img className="brand-wide" src="/brand/logo-primary.svg" alt="fam-uh-le"/><h1>Die App konnte nicht gestartet werden.</h1><p>Bitte lade die Seite vollständig neu. Falls das Problem bleibt, lösche einmal die Website-Daten bzw. den PWA-Cache.</p><details><summary>Technische Details</summary><pre style={{whiteSpace:'pre-wrap',wordBreak:'break-word'}}>{String(this.state.error?.message||this.state.error)}</pre></details><button className="primary" onClick={()=>window.location.reload()}>Neu laden</button></section></main>;
  }
}

const inviteMatch=window.location.pathname.match(/^\/invite\/([^/]+)\/?$/);
const root=document.getElementById('root');
ReactDOM.createRoot(root).render(<React.StrictMode><BootErrorBoundary><AccessibilityManager/><FeedbackHost/>{inviteMatch?<InviteFlow token={inviteMatch[1]}/>:<App/>}</BootErrorBoundary></React.StrictMode>);

if('serviceWorker' in navigator){
  window.addEventListener('load',()=>{
    const hadController=Boolean(navigator.serviceWorker.controller);
    let reloading=false;
    if(hadController){
      navigator.serviceWorker.addEventListener('controllerchange',()=>{
        if(reloading)return;
        reloading=true;
        window.location.reload();
      });
    }
    navigator.serviceWorker.register('/sw.js',{updateViaCache:'none'}).then(registration=>registration.update()).catch(error=>console.warn('Service Worker registration failed',error));
  });
}
