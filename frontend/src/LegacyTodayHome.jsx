import TodayHome from './TodayHome';
import i18n from './i18n';

export default function LegacyTodayHome({onBack,...props}){
 const de=i18n.language.startsWith('de');
 return <div data-testid="legacy-today-home">
  <div className="page-head">
   <button type="button" className="text-button" onClick={onBack}>{de?'Zurück zu Mehr':'Back to More'}</button>
   <div><small>Legacy</small><h1>{de?'Alter Legacy-Startscreen':'Legacy start screen'}</h1></div>
  </div>
  <TodayHome {...props}/>
 </div>;
}
