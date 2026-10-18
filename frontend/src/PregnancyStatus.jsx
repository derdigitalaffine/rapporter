import {formatCivilDate} from './locale';
import {Icon} from './icons';
import './pregnancy-status.css';

export default function PregnancyStatus({pregnancy,language='de',compact=false}){
 const de=language.startsWith('de'),progress=pregnancy.progress;
 const days=progress.days_until_due;
 const elapsed=Math.max(0,Math.min(280,progress.week*7+progress.day));
 return <div className={`pregnancy-status ${compact?'pregnancy-status--compact':''}`}>
  <div className="pregnancy-status-heading"><span className="pregnancy-status-icon"><Icon name="heart" size={24}/></span><div><small>{de?'Schwangerschaftswoche':'Pregnancy week'}</small><strong>{progress.week} + {progress.day}</strong></div></div>
  <dl className="pregnancy-status-facts"><div><dt>{de?'Errechneter Termin':'Estimated due date'}</dt><dd><time dateTime={pregnancy.expected_due_date}>{formatCivilDate(language,pregnancy.expected_due_date)}</time></dd></div><div><dt>{days<0?(de?'Nach errechnetem Termin':'Past estimated due date'):(de?'Bis zum errechneten Termin':'Until estimated due date')}</dt><dd>{Math.abs(days)} {de?'Tage':'days'}</dd></div></dl>
  {!compact&&<progress max={280} value={elapsed} aria-label={de?'Schwangerschaftsverlauf':'Pregnancy progress'}/>}
 </div>;
}
