import React,{useState} from 'react';
import {expect,userEvent,within} from 'storybook/test';
import {TaskEditor} from '../src/SmartEditors';
import TodoActionRow from '../src/TodoActionRow';

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
