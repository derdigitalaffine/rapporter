import React,{useState} from 'react';
import {expect,fireEvent,userEvent,within} from 'storybook/test';
import {HealthEditor,VaccinationReminderEditor} from '../src/ChildHealthPanel';
import PregnancyStatus from '../src/PregnancyStatus';
import ChildCreateForm from '../src/ChildCreateForm';
import ChildCareCircle from '../src/ChildCareCircle';
import i18n from '../src/i18n';
import '../src/baby-i18n';
import '../src/children-hub.css';

export default {title:'FamilyOS/Children'};
const c=key=>i18n.t(`childrenUi.${key}`);
export const PregnancyOverview={render:()=> <PregnancyStatus language="de" pregnancy={{expected_due_date:'2027-01-02',progress:{week:28,day:3,days_until_due:81}}}/>};
export const PregnancyPastDueDate={render:()=> <PregnancyStatus language="de" pregnancy={{expected_due_date:'2026-10-15',progress:{week:40,day:3,days_until_due:-3}}}/>};
function Reminder(){
 const [open,setOpen]=useState(false);
 return <><button onClick={()=>setOpen(true)}>An Impfungen erinnern</button>{open&&<VaccinationReminderEditor c={c} count={2} onClose={()=>setOpen(false)} onSave={async()=>{throw new Error('Speichern fehlgeschlagen')}}/>}</>;
}
export const ReminderRetainsDate={render:()=> <Reminder/>,play:async({canvasElement})=>{
 await userEvent.click(within(canvasElement).getByRole('button',{name:'An Impfungen erinnern'}));
 const dialog=within(await within(canvasElement.ownerDocument.body).findByRole('dialog',{name:'An Impfungen erinnern'}));
 const input=dialog.getByLabelText(/An Terminvereinbarung erinnern am/);
 fireEvent.change(input,{target:{value:'2030-01-02T10:30'}});
 await userEvent.click(dialog.getByRole('button',{name:'Aufgabe anlegen',exact:true}));
 await expect(dialog.getByRole('alert')).toHaveTextContent('Speichern fehlgeschlagen');
 await expect(input).toHaveValue('2030-01-02T10:30');
}};
function Editor({fail=false}){
 const [open,setOpen]=useState(false);
 return <><button onClick={()=>setOpen(true)}>Impfung dokumentieren</button>{open&&<HealthEditor row={{key:'manual:fixture',kind:'vaccination',state:'done',version:0}} c={c} onClose={()=>setOpen(false)} onSave={async()=>{if(fail)throw new Error('Speichern fehlgeschlagen');setOpen(false)}}/>}</>;
}
export const VaccinationEditor={render:()=> <Editor/>,play:async({canvasElement})=>{
 await userEvent.click(within(canvasElement).getByRole('button',{name:'Impfung dokumentieren'}));
 const dialog=within(await within(canvasElement.ownerDocument.body).findByRole('dialog'));
 await expect(dialog.getByRole('textbox',{name:'Impfung / Impfstoff'})).toBeVisible();
 await userEvent.type(dialog.getByRole('textbox',{name:'Impfung / Impfstoff'}),'Dokumentierter Impfstoff');
 await userEvent.click(dialog.getByRole('button',{name:'Weitere Angaben'}));
 await expect(dialog.getByLabelText('Charge (optional)')).toBeVisible();
}};
export const FailedSaveRetainsInput={render:()=> <Editor fail/>,play:async({canvasElement})=>{
 await userEvent.click(within(canvasElement).getByRole('button',{name:'Impfung dokumentieren'}));
 const dialog=within(await within(canvasElement.ownerDocument.body).findByRole('dialog'));
 await userEvent.type(dialog.getByRole('textbox',{name:'Impfung / Impfstoff'}),'Dokumentierter Impfstoff');
 await userEvent.click(dialog.getByRole('button',{name:'Speichern',exact:true}));
 await expect(dialog.getByRole('alert')).toHaveTextContent('Speichern fehlgeschlagen');
 await expect(dialog.getByRole('textbox',{name:'Impfung / Impfstoff'})).toHaveValue('Dokumentierter Impfstoff');
}};
export const ChildIdentity={render:()=> <ChildCreateForm family={{id:'fixture',memberships:[{id:'existing-child',role:'child',display_name:'Robin'}]}} canRecordCustody onSaved={()=>{}} onCancel={()=>{}}/>,play:async({canvasElement})=>{
 const canvas=within(canvasElement);
 await expect(canvas.getByRole('checkbox',{name:'Ich bin für dieses Kind sorgeberechtigt.'})).not.toBeChecked();
 await userEvent.selectOptions(canvas.getByLabelText('Aktives Kind'),'existing-child');
 await expect(canvas.getByRole('textbox',{name:'Name',exact:true})).toHaveValue('Robin');
}};
export const CustodyIsNotAToggle={
 beforeEach:()=>{
  const previous=globalThis.fetch;
  globalThis.fetch=(input,options)=>new URL(typeof input==='string'?input:input.url,location.href).pathname==='/api/baby/profiles/fixture/care-circle/'?Promise.resolve(Response.json({authorities:[{membership:'owner',display_name:'Alex',has_custody:true}],care_circle:[],inherited:[]})):previous(input,options);
  return()=>{globalThis.fetch=previous};
 },
 render:()=> <ChildCareCircle baby={{id:'fixture',display_name:'Robin',membership:'child'}} family={{id:'family',memberships:[]}}/>,
 play:async({canvasElement})=>{await expect(await within(canvasElement).findByText('Sorgeberechtigt · Voller Zugriff')).toBeVisible()}
};
