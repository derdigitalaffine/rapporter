import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function installCareMocks(page,operations){
 const moduleState={key:'pregnancy_baby',enabled:true,authorized:true,can_manage:true,show_in_main_navigation:true,permissions:{can_view_pregnancy:true,can_log_care:true,can_view_growth_development:true,is_guardian:true}};
 const events={'baby-1':[],'baby-2':[]};
 let nextId=1;
 await page.route('**/api/baby/**',async route=>{
  const request=route.request();const url=new URL(request.url());const path=url.pathname.replace(/^\/api/,'');const method=request.method();
  if(path==='/baby/module/')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(moduleState)});
  if(path==='/baby/pregnancies/')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({pregnancies:[]})});
  if(path==='/baby/profiles/')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({babies:[{id:'baby-1',display_name:'Mia',birth_date:'2026-08-10',growth_reference_sex:'female'},{id:'baby-2',display_name:'Noah',birth_date:'2026-08-10',growth_reference_sex:'male'}]})});
  const careMatch=path.match(/^\/baby\/profiles\/(baby-[12])\/care\/$/);
  if(careMatch){
   const babyId=careMatch[1];
   if(method==='POST'){
    const body=request.postDataJSON();const row={id:`log-${nextId++}`,version:1,created_at:new Date().toISOString(),created_by:'owner',...body};events[babyId].unshift(row);operations.push({method,path,body,id:row.id});
    return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify(row)});
   }
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({events:events[babyId],summary:{counts:{},totals:{},last:{},sleep_minutes:0}})});
  }
  const detail=path.match(/^\/baby\/care\/(log-\d+)\/$/);
  if(detail&&method==='PATCH'){
   const body=request.postDataJSON();let found=null;
   for(const rows of Object.values(events)){const row=rows.find(item=>item.id===detail[1]);if(row){found=row;break}}
   if(!found)return route.fulfill({status:404,contentType:'application/json',body:'{}'});
   found={...found,...body,version:found.version+1};
   for(const key of Object.keys(events)){events[key]=events[key].map(item=>item.id===found.id?found:item)}
   operations.push({method,path,body,id:found.id});
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(found)});
  }
  if(path.match(/^\/baby\/profiles\/baby-[12]\/viewed\/$/))return route.fulfill({status:200,contentType:'application/json',body:'{}'});
  return route.fulfill({status:200,contentType:'application/json',body:'{}'});
 });
}

test('parallel open sleep timers stay attached to each twin and bottle is one tap',async({page})=>{
 const operations=[];
 await installApiMocks(page,{language:'de'});
 await installCareMocks(page,operations);
 await page.goto('/?page=baby');
 await page.getByRole('button',{name:'Jetzt',exact:true}).click();

 const selector=page.locator('.baby-selector select');
 await expect(selector).toHaveValue('baby-1');
 const sleep=()=>page.locator('.baby-quick-grid button').filter({hasText:'Schlaf'}).first();
 await sleep().click();
 await expect(sleep()).toContainText('Timer beenden');
 expect(operations.at(-1)).toMatchObject({method:'POST',path:'/baby/profiles/baby-1/care/'});
 expect(operations.at(-1).body).toMatchObject({kind:'sleep',ended_at:null});

 await selector.selectOption('baby-2');
 await expect(sleep()).toContainText('Timer starten');
 await sleep().click();
 await expect(sleep()).toContainText('Timer beenden');
 expect(operations.at(-1)).toMatchObject({method:'POST',path:'/baby/profiles/baby-2/care/'});

 await selector.selectOption('baby-1');
 await expect(sleep()).toContainText('Timer beenden');
 await sleep().click();
 expect(operations.at(-1)).toMatchObject({method:'PATCH',path:'/baby/care/log-1/'});
 expect(operations.at(-1).body.ended_at).toBeTruthy();

 await page.getByRole('button',{name:/Flasche 90 ml/}).click();
 expect(operations.at(-1)).toMatchObject({method:'POST',path:'/baby/profiles/baby-1/care/'});
 expect(operations.at(-1).body.value.ml).toBe(90);

 await selector.selectOption('baby-2');
 await expect(sleep()).toContainText('Timer beenden');
 await sleep().click();
 expect(operations.at(-1)).toMatchObject({method:'PATCH',path:'/baby/care/log-2/'});
});
