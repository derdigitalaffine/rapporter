import CalendarSubscriptions from './CalendarSubscriptions';
import CalDavSettings from './CalDavSettings';
import {useState} from 'react';
import {readAppearance,saveAppearance} from './appearance';
import ChildPermissionsSettings from './ChildPermissionsSettings';
import './settings.css';

const SETTINGS_LINKS=[
 ['profile','Profil','Persönliche Angaben und Konto'],
 ['notifications','Benachrichtigungen','Push- und App-Benachrichtigungen'],
 ['integrations','Integrationen','Verbundene Dienste verwalten'],
 ['automations','Automationen','Regeln und automatische Abläufe'],
 ['members','Familie','Mitglieder und Rollen verwalten'],
 ['#children-permissions','Kinder & Berechtigungen','Sorgerecht und wirksame Kinderrechte einsehen'],
];
const COLOR_PROFILES=[
 ['green','Dunkelgrün','Hell','Das bekannte FamilyOS-Farbprofil','settings-swatch-green'],
 ['blue','Dunkelblau','Hell','Kühleres Blau statt Dunkelgrün','settings-swatch-blue'],
 ['green-dark','Dunkelgrün','Dunkel','Moderner dunkler Modus mit grünen Akzenten','settings-swatch-green-dark'],
 ['blue-dark','Dunkelblau','Dunkel','Moderner dunkler Modus mit blauen Akzenten','settings-swatch-blue-dark'],
];

export default function SettingsHub({open}){
 const [appearance,setAppearance]=useState(readAppearance);const familyId=localStorage.getItem('famuhle-active-family')||'';
 function update(next){setAppearance(saveAppearance({...appearance,...next}))}
 function go(page){if(page.startsWith('#')){history.replaceState(history.state,'',`${location.pathname}${location.search}${page}`);document.querySelector(page)?.scrollIntoView({behavior:'smooth',block:'start'});return}if(open)open(page);else window.location.assign(`/?page=${encodeURIComponent(page)}`)}
 return <div className="settings-page" data-page="settings">
  <section className="card settings-section" aria-labelledby="settings-design-title">
   <div><small>Darstellung</small><h2 id="settings-design-title">Design</h2><p>Wähle zwischen hellen und dunklen Farbprofilen oder aktiviere den maximal kontrastreichen Schwarz-Weiß-Modus.</p></div>
   <fieldset className="settings-choice"><legend>Farbprofil</legend>
    {COLOR_PROFILES.map(([profile,title,mode,description,swatch])=><label className="settings-option" key={profile}><input type="radio" name="color-profile" value={profile} checked={appearance.profile===profile} onChange={()=>update({profile})}/><span><strong>{title} <em>{mode}</em></strong><small>{description}</small></span><i className={`settings-swatch ${swatch}`} aria-hidden="true"/></label>)}
   </fieldset>
   <label className="settings-toggle"><span><strong>Hochkontrast Schwarz/Weiß</strong><small>Reduziert die Oberfläche auf Schwarz, Weiß und klare Konturen. Das Farbprofil bleibt gespeichert.</small></span><input type="checkbox" role="switch" checked={appearance.highContrast} onChange={event=>update({highContrast:event.target.checked})}/></label>
  </section>
  <section className="card settings-section" aria-labelledby="settings-pages-title"><div><small>Alle Bereiche</small><h2 id="settings-pages-title">App-Einstellungen</h2></div><nav className="settings-links" aria-label="Einstellungsbereiche">{SETTINGS_LINKS.map(([page,title,description])=><button type="button" key={page} onClick={()=>go(page)}><span><strong>{title}</strong><small>{description}</small></span><b aria-hidden="true">›</b></button>)}</nav></section>
  <CalendarSubscriptions key={`subscriptions-${familyId}`} familyId={familyId} settings/>
  <CalDavSettings key={`caldav-${familyId}`} familyId={familyId}/>
  <ChildPermissionsSettings familyId={familyId}/>
 </div>;
}