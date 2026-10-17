import {useId,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import './symbol-picker.css';

const names={tasks:['Aufgaben','Tasks'],shopping:['Einkauf','Shopping'],home:['Zuhause','Home'],store:['Geschäft','Store'],favorite:['Favorit','Favorite'],history:['Routine','Routine'],automation:['Putzen & Pflege','Cleaning & care'],bed:['Schlafen','Sleep'],frost:['Kühlen','Cooling'],water:['Wasser','Water'],calendar:['Kalender','Calendar'],dog:['Hund','Dog'],pet:['Haustier','Pet'],baby:['Baby','Baby'],broom:['Putzen','Cleaning'],utensils:['Essen','Meals'],car:['Auto','Car'],recycle:['Recycling','Recycling'],'bowl-food':['Füttern','Feeding'],school:['Schule','School'],heart:['Gesundheit','Health'],members:['Familie','Family'],clock:['Zeit','Time'],location:['Ort','Location'],receipt:['Beleg','Receipt'],camera:['Foto','Photo'],bolt:['Energie','Energy'],light:['Licht','Light'],weather:['Wetter','Weather'],waste:['Abfall','Waste'],route:['Unterwegs','Travel'],euro:['Geld','Money'],check:['Erledigt','Done'],book:['Lesen','Reading']};
const aliases={'list-check':'tasks','cart-shopping':'shopping',house:'home',star:'favorite',sparkles:'automation',snowflake:'frost',droplets:'water'};
export function symbolName(value){return aliases[value]||value}
export function symbolLabel(value,language='de'){return names[symbolName(value)]?.[language.startsWith('en')?1:0]||value.replaceAll('-',' ')}

// A small, native radio group: no separate combobox, modal or selection model.
export default function SymbolPicker({value,onChange,options=[],disabled=false,label}){
 const {i18n}=useTranslation(),id=useId(),de=!i18n.language.startsWith('en');
 const [query,setQuery]=useState('');const choices=[...new Set(options)];
 const visible=choices.filter(option=>`${symbolLabel(option,i18n.language)} ${option}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
 return <fieldset className="symbol-picker" disabled={disabled}><legend>{label||(de?'Symbol':'Symbol')}</legend>
  <div className="symbol-picker-current"><Icon name={symbolName(value)}/><span>{de?'Ausgewählt: ':'Selected: '}{symbolLabel(value||'',i18n.language)}</span><Icon name="check"/></div>
  {choices.length>8&&<label className="symbol-picker-search" htmlFor={`${id}-search`}><span>{de?'Symbole suchen':'Search symbols'}</span><input id={`${id}-search`} type="search" value={query} onChange={event=>setQuery(event.target.value)} placeholder={de?'Zum Beispiel Zuhause, Essen …':'For example home, meals …'}/></label>}
  <div className="symbol-picker-grid">{visible.map(option=><label key={option} className="symbol-picker-choice"><input type="radio" name={id} value={option} checked={value===option} onChange={()=>onChange(option)}/><span><Icon name={symbolName(option)} size={22}/><span>{symbolLabel(option,i18n.language)}</span>{value===option&&<Icon name="check" size={12}/>}</span></label>)}</div>
  {!visible.length&&<p role="status">{de?'Keine passenden Symbole. Versuche einen anderen Suchbegriff.':'No matching symbols. Try another search.'}</p>}
 </fieldset>
}
