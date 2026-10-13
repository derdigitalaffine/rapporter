import {useEffect,useState} from 'react';
import {createPortal} from 'react-dom';
import {readAppearance,saveAppearance} from './appearance';
import './settings.css';

const SETTINGS_LINKS=[
 ['profile','Profil','Persönliche Angaben und Konto'],
 ['notifications','Benachrichtigungen','Push- und App-Benachrichtigungen'],
 ['integrations','Integrationen','Verbundene Dienste verwalten'],
 ['automations','Automationen','Regeln und automatische Abläufe'],
 ['members','Familie','Mitglieder und Rollen verwalten'],
];
const href=page=>`/?page=${encodeURIComponent(page)}`;

export default function SettingsHub(){
 const [appearance,setAppearance]=useState(readAppearance);
 function update(next){setAppearance(saveAppearance({...appearance,...next}))}
 return <main className="settings-page content" data-page="settings">
  <div className="settings-head"><a className="back-button secondary" href="/?page=more" aria-label="Zurück">‹</a><div><small>App</small><h1>Einstellungen</h1></div></div>
  <section className="card settings-section" aria-labelledby="settings-design-title">
   <div><small>Darstellung</small><h2 id="settings-design-title">Design</h2><p>Wähle das Farbprofil der App oder aktiviere einen maximal kontrastreichen Schwarz-Weiß-Modus.</p></div>
   <fieldset className="settings-choice"><legend>Farbprofil</legend>
    <label className="settings-option"><input type="radio" name="color-profile" value="green" checked={appearance.profile==='green'} onChange={()=>update({profile:'green'})}/><span><strong>Dunkelgrün</strong><small>Das bekannte FamilyOS-Farbprofil</small></span><i className="settings-swatch settings-swatch-green" aria-hidden="true"/></label>
    <label className="settings-option"><input type="radio" name="color-profile" value="blue" checked={appearance.profile==='blue'} onChange={()=>update({profile:'blue'})}/><span><strong>Dunkelblau</strong><small>Kühleres Blau statt Dunkelgrün</small></span><i className="settings-swatch settings-swatch-blue" aria-hidden="true"/></label>
   </fieldset>
   <label className="settings-toggle"><span><strong>Hochkontrast Schwarz/Weiß</strong><small>Reduziert die Oberfläche auf Schwarz, Weiß und klare Konturen. Das Farbprofil bleibt gespeichert.</small></span><input type="checkbox" role="switch" checked={appearance.highContrast} onChange={event=>update({highContrast:event.target.checked})}/></label>
  </section>
  <section className="card settings-section" aria-labelledby="settings-pages-title"><div><small>Alle Bereiche</small><h2 id="settings-pages-title">App-Einstellungen</h2></div><nav className="settings-links" aria-label="Einstellungsbereiche">{SETTINGS_LINKS.map(([page,title,description])=><a key={page} href={href(page)}><span><strong>{title}</strong><small>{description}</small></span><b aria-hidden="true">›</b></a>)}</nav></section>
 </main>;
}

export function SettingsShortcut(){
 const [target,setTarget]=useState(null);
 useEffect(()=>{
  const locate=()=>setTarget(document.querySelector('.topbar-context'));
  locate();const observer=new MutationObserver(locate);observer.observe(document.body,{childList:true,subtree:true});return()=>observer.disconnect();
 },[]);
 if(!target)return null;
 return createPortal(<a className="settings-shortcut" href="/?page=settings" aria-label="Einstellungen" title="Einstellungen"><span aria-hidden="true">⚙</span><span className="settings-shortcut-label">Einstellungen</span></a>,target);
}
