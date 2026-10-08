import React from 'react';
import ReactDOM from 'react-dom/client';
import './i18n';
import './styles.css';
import './sheets.css';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>);
if ('serviceWorker' in navigator) window.addEventListener('load',()=>navigator.serviceWorker.register('/sw.js').catch(()=>{}));
