import React from 'react';
import ReactDOM from 'react-dom/client';
import './i18n';
import './styles.css';
import './sheets.css';
import './smart.css';
import './smart-extra.css';
import App from './App';
import InviteFlow from './InviteFlow';

const inviteMatch=window.location.pathname.match(/^\/invite\/([^/]+)\/?$/);
ReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode>{inviteMatch?<InviteFlow token={inviteMatch[1]}/>:<App/>}</React.StrictMode>);
if ('serviceWorker' in navigator) window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));
