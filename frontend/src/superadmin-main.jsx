import React from 'react';
import ReactDOM from 'react-dom/client';
import '@fontsource-variable/nunito';
import './styles.css';
import './design-system.css';
import './feedback.css';
import './superadmin.css';
import FeedbackHost from './feedback';
import SuperAdminGate from './SuperAdminGate';

function registerAdminWorker(){
  if(!('serviceWorker' in navigator))return;
  navigator.serviceWorker.register('/superadmin/sw.js',{scope:'/superadmin/',updateViaCache:'none'}).then(registration=>registration.update()).catch(error=>console.warn('Superadmin service worker registration failed',error));
}
if(document.readyState==='complete')registerAdminWorker();else window.addEventListener('load',registerAdminWorker,{once:true});

ReactDOM.createRoot(document.getElementById('root')).render(<React.StrictMode><FeedbackHost/><SuperAdminGate/></React.StrictMode>);
