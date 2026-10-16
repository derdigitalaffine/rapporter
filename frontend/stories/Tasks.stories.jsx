import React,{useState} from 'react';
import {expect,userEvent,within,waitFor} from 'storybook/test';
import {TaskEditor} from '../src/SmartEditors';
import TodoActionRow from '../src/TodoActionRow';
import ActionCapture from '../src/ActionCapture';
import FamilySheet from '../src/ui/FamilySheet';

export default {title:'FamilyOS/Tasks'};
export const CompactAction={render:()=> <TodoActionRow language="de" item={{id:'task:fixture',kind:'task',title:'Ein gemeinsames Aufgabenobjekt mit einem langen deutschen Titel',state:'open',context:{},primary_action:{id:'complete'},allowed_actions:[]}}/>};
function Dialog(){const [open,setOpen]=useState(false);return <><button type="button" className="primary" onClick={()=>setOpen(true)}>Aufgabe hinzufügen</button>{open&&<TaskEditor family={{id:'fixture-family',memberships:[]}} lists={[]} onClose={()=>setOpen(false)} onSaved={()=>setOpen(false)}/>}</>}
export const CreateDialog={render:()=> <Dialog/>,play:async({canvasElement})=>{
 const canvas=within(canvasElement),body=within(canvasElement.ownerDocument.body);
 const trigger=canvas.getByRole('button',{name:'Aufgabe hinzufügen'});
 await userEvent.click(trigger);
 const dialog=await body.findByRole('dialog');
 await expect(within(dialog).getByRole('textbox',{name:'Titel',exact:true})).toBeVisible();
 await expect(within(dialog).getByRole('button',{name:'Speichern',exact:true})).toBeDisabled();
 await userEvent.click(within(dialog).getByRole('button',{name:'Schließen',exact:true}));
 await expect(trigger).toHaveFocus();
}};

function CaptureDialog(){const [open,setOpen]=useState(false);return <><button type="button" onClick={()=>setOpen(true)}>Erledigt erfassen</button>{open&&<FamilySheet labelledBy="capture-story-title" onClose={()=>setOpen(false)}><h2 id="capture-story-title">Erledigt erfassen</h2><button type="button" className="sheet-close" aria-label="Schließen" onClick={()=>setOpen(false)}>X</button><ActionCapture family={{id:'fixture-family'}}/></FamilySheet>}</>}
export const CaptureDetails={render:()=> <CaptureDialog/>,play:async({canvasElement})=>{
 const canvas=within(canvasElement),body=within(canvasElement.ownerDocument.body);
 const trigger=canvas.getByRole('button',{name:'Erledigt erfassen'});
 await userEvent.click(trigger);
 const dialog=within(await body.findByRole('dialog'));
 await userEvent.click(dialog.getByRole('button',{name:'Dauer und Vorschläge'}));
 const duration=dialog.getByLabel('Dauer (optional)');
 await expect(duration).toBeVisible();
 await userEvent.selectOptions(duration,'10');
 await expect(duration).toHaveValue('10');
 await userEvent.click(dialog.getByRole('button',{name:'Schließen'}));
 await waitFor(()=>expect(trigger).toHaveFocus());
}};

function Edit(){const [open,setOpen]=useState(false);return <><button type="button" onClick={()=>setOpen(true)}>Aufgabe bearbeiten</button>{open&&<TaskEditor task={{id:'fixture-task',family:'fixture-family',title:'Bestehende Aufgabe mit Details',due_at:'2026-10-16T16:00:00Z',notes:'Weitere Informationen',assignee:9001}} family={{id:'fixture-family'}} members={[{user:9001,display_name:'Alex'}]} onClose={()=>setOpen(false)} onSaved={()=>setOpen(false)}/>}</>}
export const EditDialog={
 beforeEach:()=>{
  const previous=globalThis.fetch;
  globalThis.fetch=(input,options)=>{
   const url=new URL(typeof input==='string'?input:input.url,location.href);
   if(url.pathname==='/api/actions/task/fixture-task/')return Promise.resolve(Response.json({id:'fixture-action'}));
   if(url.pathname==='/api/actions/')return Promise.resolve(Response.json({actions:[{id:'task:fixture-task',allowed_actions:[{id:'duel',href:'/?page=games&task=fixture-task'}]}]}));
   if(url.pathname==='/api/scheduling/dependencies/')return Promise.resolve(Response.json({dependencies:[],origins:[]}));
   return previous(input,options);
  };
  return()=>{globalThis.fetch=previous};
 },
 render:()=> <Edit/>,play:async({canvasElement})=>{
  const canvas=within(canvasElement),body=within(canvasElement.ownerDocument.body);
  const trigger=canvas.getByRole('button',{name:'Aufgabe bearbeiten'});
  await userEvent.click(trigger);
  const dialog=within(await body.findByRole('dialog'));
  const action=await dialog.findByRole('button',{name:'Zuweisung ausspielen'});
  action.scrollIntoView({block:'center'});
  await waitFor(()=>{
   const box=action.getBoundingClientRect();const hit=action.ownerDocument.elementFromPoint(box.x+box.width/2,box.y+box.height/2);
   expect(action.contains(hit)).toBe(true);
  });
  await expect(dialog.getByLabel('Notizen')).toHaveValue('Weitere Informationen');
  await userEvent.click(dialog.getByRole('button',{name:'Schließen'}));
  await waitFor(()=>expect(trigger).toHaveFocus());
 }
};
