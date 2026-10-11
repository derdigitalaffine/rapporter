import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const family='family-1';
const initialDecision=()=>({
 id:'11111111-1111-4111-8111-111111111111',family,question:'Pizza oder Pasta?',mode:'single',anonymous:false,closes_at:null,closed_at:null,is_open:true,created_at:'2026-10-11T00:00:00Z',total_voters:0,can_vote:true,can_close:true,my_option_ids:[],context:null,
 options:[
  {id:'22222222-2222-4222-8222-222222222222',label:'Pizza',position:0,votes:0,selected_by_me:false,voters:[]},
  {id:'33333333-3333-4333-8333-333333333333',label:'Pasta',position:1,votes:0,selected_by_me:false,voters:[]},
 ]
});

async function installDecisionApi(page){
 let rows=[initialDecision()];
 await page.route('**/api/decisions/**',async route=>{
  const request=route.request();const url=new URL(request.url());const method=request.method();let body={};try{body=request.postDataJSON()||{}}catch{}
  const json=(payload,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(payload)});
  if(url.pathname==='/api/decisions/'&&method==='GET')return json({count:rows.length,results:rows});
  if(url.pathname==='/api/decisions/'&&method==='POST'){
   const created={...initialDecision(),id:'44444444-4444-4444-8444-444444444444',question:body.question,mode:body.mode,anonymous:body.anonymous,options:body.options.map((label,index)=>({id:`55555555-5555-4555-8555-55555555555${index}`,label,position:index,votes:0,selected_by_me:false,...(body.anonymous?{}:{voters:[]})}))};rows=[created,...rows];return json(created,201);
  }
  const vote=url.pathname.match(/^\/api\/decisions\/([^/]+)\/vote\/$/);
  if(vote&&method==='POST'){
   const row=rows.find(item=>item.id===vote[1]);const selected=new Set(body.option_ids||[]);row.my_option_ids=[...selected];row.total_voters=selected.size?1:0;row.options=row.options.map(option=>({...option,votes:selected.has(option.id)?1:0,selected_by_me:selected.has(option.id),...(row.anonymous?{}:{voters:selected.has(option.id)?[{membership:'member-1',name:'Alex'}]:[]})}));return json(row);
  }
  const close=url.pathname.match(/^\/api\/decisions\/([^/]+)\/close\/$/);
  if(close&&method==='POST'){const row=rows.find(item=>item.id===close[1]);row.is_open=false;row.closed_at='2026-10-11T01:00:00Z';row.can_vote=false;return json(row)}
  return route.fallback();
 });
}

test('decision voting is keyboard accessible and stays within the mobile viewport',async({page})=>{
 await installApiMocks(page,{dismissOnboarding:true});
 await installDecisionApi(page);
 await page.goto('/?page=decisions');
 await expect(page.getByRole('heading',{name:'Entscheidungen'})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Pizza oder Pasta?'})).toBeVisible();
 const pizza=page.getByRole('radio',{name:/Pizza/});
 await pizza.focus();
 await page.keyboard.press('Space');
 await expect(pizza).toBeChecked();
 const save=page.getByRole('button',{name:'Stimme speichern'});
 await save.focus();
 await page.keyboard.press('Enter');
 await expect(page.getByText('Stimme gespeichert.')).toBeVisible();
 await expect(page.getByText('1 Stimmen')).toBeVisible();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
 expect(overflow).toBe(false);
});

test('family member can create and close a standalone decision',async({page})=>{
 await installApiMocks(page,{dismissOnboarding:true});
 await installDecisionApi(page);
 await page.goto('/?page=decisions');
 await page.getByRole('button',{name:'Neue Entscheidung'}).click();
 await page.getByLabel('Frage').fill('Wohin am Sonntag?');
 await page.getByPlaceholder('Option 1').fill('Zoo');
 await page.getByPlaceholder('Option 2').fill('See');
 await page.getByRole('button',{name:'Entscheidung erstellen'}).click();
 const heading=page.getByRole('heading',{name:'Wohin am Sonntag?'});
 await expect(heading).toBeVisible();
 const card=heading.locator('xpath=ancestor::article');
 await card.getByRole('button',{name:'Entscheidung schließen'}).click();
 await expect(card.getByText('Geschlossen')).toBeVisible();
});
