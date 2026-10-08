import React from 'react';
import ReactDOM from 'react-dom/client';
import './i18n';
import './styles.css';
import './sheets.css';
import App from './App';
import InviteFlow from './InviteFlow';

const inviteMatch=window.location.pathname.match(/^\/invite\/([^/]+)\/?$/);
const root=inviteMatch?<InviteFlow token={decodeURIComponent(inviteMatch[1])}/>:<App/>;
ReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode>{root}</React.StrictMode>);
if ('serviceWorker' in navigator) window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));
