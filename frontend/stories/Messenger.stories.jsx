import React,{useState} from 'react';
import {expect,userEvent,within} from 'storybook/test';
import MessengerThread from '../src/MessengerThread';
import SymbolPicker from '../src/SymbolPicker';
import '../src/messenger-i18n';
import '../src/messenger.css';
export default {title:'FamilyOS/Messenger'};
function fixture({empty=false,error=false,readonly=false}={}){return()=>{
 const previous=globalThis.fetch;
 const chat={id:'fixture',kind:'direct',title:'Kim',state:'active',can_send:!readonly,participants:[],typing:[],read_receipts:[]};
 const rows=empty?[]:[{id:'message',sender_id:2,sender_name:'Kim',sequence:1,event_sequence:1,body:'Wir treffen uns am Spielplatz. Hier ist der Treffpunkt.',created_at:'2026-10-17T12:00:00Z',attachments:[],reactions:[],location:{latitude:52.52,longitude:13.405,accuracy:12}}];
 globalThis.fetch=(input,options)=>{const url=new URL(typeof input==='string'?input:input.url,location.href);if(url.pathname.startsWith('/api/chat/')){if(options?.method==='POST'&&url.pathname.endsWith('/messages/'))return Promise.resolve(Response.json({detail:'temporary'},{status:503}));if(error)return Promise.resolve(Response.json({detail:'temporary'},{status:503}));return Promise.resolve(Response.json(url.pathname.includes('/messages/')?{results:rows,cursor:1,has_more:false,conversation:chat}:{ok:true}))}return previous(input,options)};
 return()=>{globalThis.fetch=previous};
}}
const Thread=()=> <div className="messenger-page" style={{height:'min(700px,85dvh)'}}><MessengerThread chatId="fixture" userId={1} onBack={()=>{}} onChanged={()=>{}}/></div>;
export const Conversation={beforeEach:fixture(),render:Thread};
export const Empty={beforeEach:fixture({empty:true}),render:Thread};
export const Unavailable={beforeEach:fixture({error:true}),render:Thread};
export const ReadOnly={beforeEach:fixture({readonly:true}),render:Thread};
export const FailedSend={beforeEach:fixture(),render:Thread,play:async({canvasElement})=>{const canvas=within(canvasElement);const field=await canvas.findByRole('textbox',{name:'Nachricht',exact:true});await userEvent.type(field,'Mein Entwurf bleibt erhalten');await userEvent.click(canvas.getByRole('button',{name:'Senden',exact:true}));await expect(await canvas.findByRole('alert')).toHaveTextContent('Nicht gesendet');await expect(field).toHaveValue('Mein Entwurf bleibt erhalten')}};
function Symbols({disabled=false}){const [value,setValue]=useState('tasks');return <SymbolPicker value={value} onChange={setValue} disabled={disabled} options={['tasks','shopping','home','store','favorite','history','bed','water','calendar','dog','pet','broom','utensils','school']}/>}
export const SymbolsSearch={render:()=> <Symbols/>,play:async({canvasElement})=>{const canvas=within(canvasElement);await userEvent.type(canvas.getByRole('searchbox'),'zuhause');const radio=canvas.getByRole('radio',{name:'Zuhause'});await userEvent.click(radio);await expect(radio).toBeChecked();await userEvent.clear(canvas.getByRole('searchbox'));radio.focus();await userEvent.keyboard('{ArrowRight}');await expect(canvas.getByRole('radio',{name:'Geschäft'})).toBeChecked()}};
export const SymbolsDisabled={render:()=> <Symbols disabled/>};
