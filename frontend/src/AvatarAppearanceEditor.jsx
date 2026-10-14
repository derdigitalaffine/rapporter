import {useMemo,useState} from 'react';
import {Icon} from './icons';
import './avatar-appearance-editor.css';

const GROUPS=[
 {key:'people',label:'Person & Familie',icons:['user','members','baby','heart','favorite']},
 {key:'animals',label:'Tiere',icons:['pet','dog']},
 {key:'home',label:'Zuhause',icons:['home','bed','utensils','water','broom','shopping','store','lists','recycle']},
 {key:'activities',label:'Aktivitäten',icons:['play','microphone','camera','tasks','calendar','clock','progress','priority','bolt','light','hot']},
 {key:'places',label:'Unterwegs',icons:['car','transit','route','location','school','weather','rain','frost']},
 {key:'other',label:'Mehr',icons:['robot','inbox','email','link','share','receipt','archive','sliders','tags','trend','automation','integrations','waste','install','settle','euro','send']},
];

export default function AvatarAppearanceEditor({value,onChange,hasPhoto=false,disabled=false,t}){
 const [advanced,setAdvanced]=useState(false);
 const [query,setQuery]=useState('');
 const options=value?.avatar_icon_options||[];
 const palette=value?.avatar_color_palette||[];
 const mode=value?.avatar_mode||'initials';
 const update=patch=>onChange?.({...value,...patch});
 const groups=useMemo(()=>GROUPS.map(group=>({...group,icons:group.icons.filter(icon=>options.includes(icon)&&(!query||icon.toLowerCase().includes(query.trim().toLowerCase())))})).filter(group=>group.icons.length),[options,query]);
 function chooseMode(next){if(disabled)return;if(next==='photo'&&!hasPhoto)return;if(next==='icon'&&!value?.avatar_icon_key){update({avatar_mode:'icon',avatar_icon_key:options[0]||'user'});return}update({avatar_mode:next})}
 function chooseIcon(icon){update({avatar_mode:'icon',avatar_icon_key:icon})}
 return <section className="avatar-appearance-editor">
  <fieldset className="avatar-mode-field"><legend>{t('profileUi.avatarStyle')}</legend><div className="avatar-mode-grid">
   <button type="button" className={mode==='initials'?'selected':''} aria-pressed={mode==='initials'} disabled={disabled} onClick={()=>chooseMode('initials')}><span className="avatar-mode-preview">Aa</span><strong>{t('profileUi.avatarInitials')}</strong><small>{t('profileUi.avatarInitialsHint')}</small></button>
   <button type="button" className={mode==='icon'?'selected':''} aria-pressed={mode==='icon'} disabled={disabled} onClick={()=>chooseMode('icon')}><span className="avatar-mode-preview"><Icon name={value?.avatar_icon_key||'favorite'}/></span><strong>{t('profileUi.avatarSymbol')}</strong><small>{t('profileUi.avatarSymbolHint')}</small></button>
   <button type="button" className={mode==='photo'?'selected':''} aria-pressed={mode==='photo'} disabled={disabled||!hasPhoto} onClick={()=>chooseMode('photo')}><span className="avatar-mode-preview"><Icon name="camera"/></span><strong>{t('profileUi.avatarPhoto')}</strong><small>{hasPhoto?t('profileUi.avatarPhotoHint'):t('profileUi.avatarPhotoMissing')}</small></button>
  </div></fieldset>
  {mode==='icon'&&<fieldset className="avatar-symbol-field"><legend>{t('profileUi.avatarChooseSymbol')}</legend><label className="avatar-symbol-search"><span className="sr-only">{t('profileUi.avatarSymbolSearch')}</span><Icon name="search"/><input type="search" value={query} disabled={disabled} placeholder={t('profileUi.avatarSymbolSearch')} onChange={e=>setQuery(e.target.value)}/></label><div className="avatar-symbol-groups">{groups.map(group=><section key={group.key}><small>{group.label}</small><div className="avatar-symbol-grid">{group.icons.map(icon=><button type="button" key={icon} aria-label={icon} aria-pressed={value?.avatar_icon_key===icon} className={value?.avatar_icon_key===icon?'selected':''} disabled={disabled} onClick={()=>chooseIcon(icon)}><Icon name={icon}/></button>)}</div></section>)}</div></fieldset>}
  <fieldset className="avatar-color-field"><legend>{t('profileUi.avatarColor')}</legend><small>{t('profileUi.avatarColorHint')}</small><div className="profile-color-picker" role="group" aria-label={t('profileUi.avatarColor')}>{palette.map((color,index)=><button key={color} type="button" className="profile-color-swatch" style={{backgroundColor:color}} aria-pressed={(value?.avatar_color||'').toUpperCase()===color.toUpperCase()} aria-label={t('profileUi.avatarColorOption',{number:index+1})} title={color} disabled={disabled} onClick={()=>update({avatar_color:color})}/>)}</div><button type="button" className="text-button avatar-advanced-toggle" aria-expanded={advanced} disabled={disabled} onClick={()=>setAdvanced(v=>!v)}>{advanced?t('profileUi.avatarHideAdvanced'):t('profileUi.avatarAdvanced')}</button>{advanced&&<label className="avatar-custom-color">{t('profileUi.avatarCustomColor')}<input type="color" value={value?.avatar_color||palette[0]||'#2F6F73'} disabled={disabled} onChange={e=>update({avatar_color:e.target.value.toUpperCase()})}/><code>{value?.avatar_color||''}</code></label>}</fieldset>
 </section>;
}
