import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const family='family-1';
const initialDecision=()=>({
 id:'11111111-1111-4111-8111-111111111111',family,question:'Pizza oder Pasta?',mode:'single',anonymous:false,closes_at:null,closed_at:null,is_open:true,created_at:'2026-10-11T00:00:00Z',total_voters:0,can_vote:true,can_close:true,my_option_ids:[],context:null,
 result:{metric:'votes',winner:null,leaders:[],is_tie:false},
 options:[
  {id:'22222222-2222-4222-8222-222222222222',label:'Pizza',position:0,votes:0,selected_by_me:false,average_rank:null,average_score:null,my_rank:null,my_score:null,voters:[]},
  {id:'33333333-3333-4333-8333-333333333333',label:'Pasta',position:1,votes:0,selected_by_me:false,average_rank:null,average_score:null,my_rank:null,my_score:null,voters:[]},
 ]
});

function updateResult(row){
 if(row.mode==='ranking'){
  const ranked=row.options.filter(option=>option.average_rank!=null).sort((a,b)=>a.average_rank-b.average_rank);
  row.result={metric:'average_rank',winner:ranked[0]?{id:ranked[0].id,label:ranked[0].label,value:ranked[0].average_rank}:null,leaders:ranked[0]?[{id:ranked[0].id,label:ranked[0].label,value:ranked[0].average_rank}]:[],is_tie:false};
  return;
 }
 if(row.mode==='rating'){
  const rated=row.options.filter(option=>option.average_score!=null).sort((a,b)=>b.average_score-a.average_score);
  row.result={metric:'average_score',winner:rated[0]?{id:rated[0].id,label:rated[0].label,value:rated[0].average_score}:null,leaders:rated[0]?[{id:rated[0].id,label:rated[0].label,value:rated[0].average_score}]:[],is_tie:false};
  return;
 }
 const max=Math.max(0,...row.options.map(option=>option.votes||0));
 const leaders=max?row.options.filter(option=>option.votes===max).map(option=>({id:option.id,label:option.label,value:max})):[];
 row.result={metric:'votes',winner:leaders.length===1?leaders[0]:null,leaders,is_tie:leaders.length>1};
}

async function installDecisionApi(page){
 let rows=[initialDecision()];
 await page.route('**/api/decisions/**',async route=>{
  const request=route.request();const url=new URL(request.url());const method=request.method();let body={};try{body=request.postDataJSON()||{}}catch{}
  const json=(payload,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(payload)});
  if(url.pathname==='/api/decisions/'&&method==='GET')return json({count:rows.length,results:rows});
  if(url.pathname==='/api/decisions/'&&method==='POST'){
   const created={...initialDecision(),id:'44444444-4444-4444-8444-444444444444',question:body.question,mode:body.mode,anonymous:body.anonymous,options:body.options.map((label,index)=>({id:`55555555-5555-4555-8555-55555555555${index}`,label,position:index,votes:0,selected_by_me:false,average_rank:null,average_score:null,my_rank:null,my_score:null,...(body.anonymous?{}:{voters:[]})}))};
   updateResult(created);rows=[created,...rows];return json(created,201);
  }
  const vote=url.pathname.match(/^\/api\/decisions\/([^/]+)\/vote\/$/);
  if(vote&&method==='POST'){
   const row=rows.find(item=>item.id===vote[1]);
   if(row.mode==='rating'){
    const scores=new Map((body.ratings||[]).map(item=>[item.option_id,item.score]));
    row.my_option_ids=[];row.total_voters=scores.size?1:0;
    row.options=row.options.map(option=>{const score=scores.get(option.id)??null;return {...option,votes:score==null?0:1,selected_by_me:score!=null,my_score:score,average_score:score,my_rank:null,average_rank:null,...(row.anonymous?{}:{voters:score==null?[]:[{membership:'member-1',name:'Alex',score}]})}});
   }else if(row.mode==='ranking'){
    const ordered=body.option_ids||[];const ranks=new Map(ordered.map((id,index)=>[id,index+1]));
    row.my_option_ids=ordered;row.total_voters=ordered.length?1:0;
    row.options=row.options.map(option=>{const rank=ranks.get(option.id)??null;return {...option,votes:rank==null?0:1,selected_by_me:rank!=null,my_rank:rank,average_rank:rank,my_score:null,average_score:null,...(row.anonymous?{}:{voters:rank==null?[]:[{membership:'member-1',name:'Alex',rank}]})}});
   }else{
    const selected=new Set(body.option_ids||[]);row.my_option_ids=[...selected];row.total_voters=selected.size?1:0;
    row.options=row.options.map(option=>({...option,votes:selected.has(option.id)?1:0,selected_by_me:selected.has(option.id),...(row.anonymous?{}:{voters:selected.has(option.id)?[{membership:'member-1',name:'Alex'}]:[]})}));
   }
   updateResult(row);return json(row);
  }
  const close=url.pathname.match(/^\/api\/decisions\/([^/]+)\/close\/$/);
  if(close&&method==='POST'){const row=rows.find(item=>item.id===close[1]);row.is_open=false;row.closed_at='2026-10-11T01:00:00Z';row.can_vote=false;return json(row)}
  return route.fallback();
 });
}

async function createDecision(page,{question,mode='single',options=['Zoo','See']}){
 await page.getByRole('button',{name:'Neue Entscheidung'}).click();
 await page.getByLabel('Frage').fill(question);
 await page.getByLabel('Abstimmungsart').selectOption(mode);
 for(const [index,label] of options.entries())await page.getByLabel(`Option ${index+1}`).fill(label);
 await page.getByRole('button',{name:'Entscheidung erstellen'}).click();
 const heading=page.getByRole('heading',{name:question});
 await expect(heading).toBeVisible();
 return heading.locator('xpath=ancestor::article');
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
 const card=await createDecision(page,{question:'Wohin am Sonntag?'});
 await card.getByRole('button',{name:'Entscheidung schließen'}).click();
 await expect(card.getByText('Geschlossen')).toBeVisible();
});

test('ranking can be reordered without drag and submitted with keyboard-friendly controls',async({page})=>{
 await installApiMocks(page,{dismissOnboarding:true});
 await installDecisionApi(page);
 await page.goto('/?page=decisions');
 const card=await createDecision(page,{question:'Welche Anschaffung zuerst?',mode:'ranking',options:['Fahrrad','Grill']});
 await expect(card.getByText('Bringe alle Optionen in deine bevorzugte Reihenfolge.')).toBeVisible();
 await card.getByRole('button',{name:'Nach unten: Fahrrad'}).click();
 const rows=card.locator('.decision-ranking-row');
 await expect(rows.nth(0)).toContainText('Grill');
 await expect(rows.nth(1)).toContainText('Fahrrad');
 await card.getByRole('button',{name:'Stimme speichern'}).click();
 await expect(card.getByText('Ø Rang 1')).toBeVisible();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
 expect(overflow).toBe(false);
});

test('rating uses explicit 1 to 5 controls and saves partial ratings',async({page})=>{
 await installApiMocks(page,{dismissOnboarding:true});
 await installDecisionApi(page);
 await page.goto('/?page=decisions');
 const card=await createDecision(page,{question:'Welche Unterkunft passt?',mode:'rating',options:['Hotel','Ferienwohnung']});
 await expect(card.getByText('Bewerte eine oder mehrere Optionen von 1 bis 5.')).toBeVisible();
 const hotel=card.locator('.decision-rating-row').filter({hasText:'Hotel'});
 const score=hotel.getByRole('radio',{name:'5'});
 await score.focus();
 await page.keyboard.press('Space');
 await expect(score).toBeChecked();
 await card.getByRole('button',{name:'Stimme speichern'}).click();
 await expect(hotel.getByText('Durchschnitt 5/5')).toBeVisible();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
 expect(overflow).toBe(false);
});
