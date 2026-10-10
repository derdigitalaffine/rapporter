import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function installCareMocks(page,posts){
 const moduleState={key:'pregnancy_baby',enabled:true,authorized:true,can_manage:true,show_in_main_navigation:true,permissions:{can_view_pregnancy:true,can_log_care:true,can_view_growth_development:true,is_guardian:true}};
 await page.route('**/api/baby/**',async route=>{
  const request=route.request();const url=new URL(request.url());const path=url.pathname.replace(/^\/api/,'');const method=request.method();
  if(path==='/baby/module/')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(moduleState)});
  if(path==='/baby/pregnancies/')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({pregnancies:[]})});
  if(path==='/baby/profiles/')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({babies:[{id:'baby-1',display_name:'Mia',birth_date:'2026-08-10',growth_reference_sex:'female'},{id:'baby-2',display_name:'Noah',birth_date:'2026-08-10',growth_reference_sex:'male'}]})});
  if(path.match(/^\/baby\/profiles\/baby-[12]\/care\/$/)){
   if(method==='POST'){posts.push({path,body:request.postDataJSON()});return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({id:`log-${posts.length}`,version:1,...request.postDataJSON()})})}
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({events:[],summary:{counts:{},totals:{},last:{},sleep_minutes:0}})});
  }
  if(path.match(/^\/baby\/profiles\/baby-[12]\/viewed\/$/))return route.fulfill({status:200,contentType:'application/json',body:'{}'});
  return route.fulfill({status:200,contentType:'application/json',body:'{}'});
 });
}

test('parallel sleep timers stay attached to the selected twin and bottle is one tap',async({page})=>{
 const posts=[];
 await installApiMocks(page,{language:'de'});
 await installCareMocks(page,posts);
 await page.goto('/?page=baby');
 await page.getByRole('button',{name:'Jetzt',exact:true}).click();

 const selector=page.locator('.baby-selector select');
 await expect(selector).toHaveValue('baby-1');
 const sleep=()=>page.locator('.baby-quick-grid button').filter({hasText:'Schlaf'}).first();
 await sleep().click();
 await expect(sleep()).toContainText('Timer beenden');

 await selector.selectOption('baby-2');
 await expect(sleep()).toContainText('Timer starten');
 await sleep().click();
 await expect(sleep()).toContainText('Timer beenden');

 await selector.selectOption('baby-1');
 await expect(sleep()).toContainText('Timer beenden');
 await sleep().click();
 expect(posts.at(-1).path).toBe('/baby/profiles/baby-1/care/');
 expect(posts.at(-1).body.kind).toBe('sleep');

 await page.getByRole('button',{name:/Flasche 90 ml/}).click();
 expect(posts.at(-1).path).toBe('/baby/profiles/baby-1/care/');
 expect(posts.at(-1).body.value.ml).toBe(90);

 await selector.selectOption('baby-2');
 await expect(sleep()).toContainText('Timer beenden');
 await sleep().click();
 expect(posts.at(-1).path).toBe('/baby/profiles/baby-2/care/');
 expect(posts.at(-1).body.kind).toBe('sleep');
});
