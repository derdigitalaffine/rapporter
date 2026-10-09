import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const prediction={
  key:'waschmittel',
  name:'Waschmittel',
  prediction:{status:'due',expected_interval_days:30,confidence:.84,purchase_count:5,days_since_purchase:31,days_until_expected:-1},
  defaults:{quantity:'1',category:'Haushalt',aisle:'Reinigung',store:'Markt'},
};

test('routine editor uses learned forecast instead of manual interval',async({page})=>{
  const state=await installApiMocks(page);
  state.routines.push({
    id:'routine-1',family:'family-1',name:'Bad putzen',icon:'history',active:true,
    last_done_at:new Date(Date.now()-7*86400000).toISOString(),logs:[],
    prediction:{status:'due',expected_interval_days:7,confidence:.84,sample_count:5,interval_count:4,days_until_expected:0},
  });

  await page.goto('/?page=routines');
  await page.getByRole('button',{name:/Bad putzen/}).click();

  const dialog=page.getByRole('dialog');
  await expect(dialog).toContainText('Wahrscheinlich wieder dran');
  await expect(dialog).toContainText('Meist etwa alle 7 Tage');
  await expect(dialog.getByText(/Intervall/i)).toHaveCount(0);
  await expect(dialog.locator('input[type="number"]')).toHaveCount(0);
});

test('shopping prediction can be accepted explicitly without layout overflow',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page);
  let suggestions=[prediction];
  let acceptedBody=null;
  await page.route('**/api/shopping-predictions/**',async route=>{
    const request=route.request();const url=new URL(request.url());const path=url.pathname;let body={};try{body=request.postDataJSON()||{}}catch{}
    if(path==='/api/shopping-predictions/'&&request.method()==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({generated_at:new Date().toISOString(),suggestions})});
    if(path==='/api/shopping-predictions/accept/'&&request.method()==='POST'){
      acceptedBody=body;suggestions=[];
      return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({created:true,item:{id:'predicted-item',shopping_list:'shop-1',name:'Waschmittel',quantity:'1',category:'Haushalt',aisle:'Reinigung',checked:false}})});
    }
    return route.fallback();
  });

  await page.goto('/?page=shopping');
  const panel=page.locator('.shopping-predictions');
  await expect(panel).toContainText('Wahrscheinlich bald wieder nötig');
  await expect(panel).toContainText('Waschmittel');
  await panel.getByRole('button',{name:'Hinzufügen'}).click();

  await expect.poll(()=>acceptedBody?.key).toBe('waschmittel');
  await expect(panel).toHaveCount(0);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test('shopping prediction can be dismissed without adding it',async({page})=>{
  await installApiMocks(page);
  let suggestions=[prediction];
  let feedback=null;
  await page.route('**/api/shopping-predictions/**',async route=>{
    const request=route.request();const url=new URL(request.url());const path=url.pathname;let body={};try{body=request.postDataJSON()||{}}catch{}
    if(path==='/api/shopping-predictions/'&&request.method()==='GET')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({generated_at:new Date().toISOString(),suggestions})});
    if(path==='/api/shopping-predictions/feedback/'&&request.method()==='POST'){
      feedback=body;suggestions=[];
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({key:body.key,action:body.action,suppress_until:new Date(Date.now()+86400000).toISOString(),dismiss_count:1})});
    }
    return route.fallback();
  });

  await page.goto('/?page=shopping');
  const panel=page.locator('.shopping-predictions');
  await panel.getByRole('button',{name:/Waschmittel: Diesen Vorschlag ausblenden/}).click();
  await expect.poll(()=>feedback?.action).toBe('dismissed');
  await expect(panel).toHaveCount(0);
});
