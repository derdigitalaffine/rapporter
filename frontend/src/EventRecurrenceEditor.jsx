import SchedulingRecurrenceEditor,{recurrenceObject} from './SchedulingRecurrenceEditor';

export {recurrenceObject};

export default function EventRecurrenceEditor({value,onChange,disabled=false,familyId,anchor}){
 return <SchedulingRecurrenceEditor value={value} onChange={onChange} disabled={disabled} familyId={familyId} anchor={anchor} allowOnce={false} allowNone/>;
}
