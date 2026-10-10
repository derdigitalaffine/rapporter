import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function installBabyMocks(page,{enabled=true,authorized=true,canManage=true,showInNav=true}={}){
  const moduleState={
    key:'pregnancy_baby',enabled,authorized,can_manage:canManage,show_in_main_navigation:showInNav,
    permissions:authorized?{can_view_pregnancy:true,can_log_care:true,can_view_growth_development:true,is_guardian:canManage}:null,
  };
  await page.route('**/api/baby/**',async route=>{
    const request=route.request();const url=new URL(request.url());const path=url.pathname.replace(/^\/api/,'');const method=request.method();
    if(path==='/baby/module/'){
      if(method==='PATCH'){let body={};try{body=request.postDataJSON()||{}}catch{};Object.assign(moduleState,body);if(body.enabled===true)moduleState.authorized=true;return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(moduleState)})}
      return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(moduleState)});
    }
    if(path==='/baby/pregnancies/')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({pregnancies:[]})});
    if(path==='/baby/profiles/')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({babies:[{id:'baby-1',display_name:'Mia',birth_date:'2026-08-10',growth_reference_sex:'female'}]})});
    if(path==='/baby/care-circle/')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({care_circle:[]})});
    if(path==='/baby/profiles/baby-1/care/')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({events:[],summary:{counts:{},last_by_kind:{}}})});
    if(path==='/baby/profiles/baby-1/growth/')return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({reference:{key:'who_2006'},points:[]})});
    if(path.startsWith('/baby/profiles/baby-1/development/'))return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({source:{version:'2026-02-16'},checklist_age_months:2,interpretation:'Observation prompts, not a diagnosis.',items:[]})});
    return route.fulfill({status:200,contentType:'application/json',body:'{}'});
  });
  return moduleState;
}

test('Pregnancy & Baby stays private, reload-safe and responsive in German',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{language:'de'});
  await installBabyMocks(page,{enabled:true,authorized:true,canManage:true,showInNav:true});
  await page.goto('/');
  const nav=page.locator('.bottom-nav');
  await expect(nav.getByRole('button',{name:'Baby',exact:true})).toBeVisible();
  expect(await nav.evaluate(el=>getComputedStyle(el).position)).toBe('fixed');
  await nav.getByRole('button',{name:'Baby',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Schwangerschaft & Baby'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.reload();
  await expect(page.getByRole('heading',{name:'Schwangerschaft & Baby'})).toBeVisible();
  await expect(page.getByText(/Care Circle/).first()).toBeVisible();
});

test('disabled module is opt-in and usable in English without entering main nav',async({page})=>{
  await installApiMocks(page,{language:'en'});
  await installBabyMocks(page,{enabled:false,authorized:false,canManage:true,showInNav:false});
  await page.goto('/?page=more');
  await expect(page.locator('.bottom-nav').getByRole('button',{name:'Baby',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Pregnancy & Baby',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Pregnancy & Baby'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Enable module'})).toBeVisible();
});

test('member outside Care Circle gets no Pregnancy & Baby navigation entry',async({page})=>{
  await installApiMocks(page,{language:'de'});
  await installBabyMocks(page,{enabled:true,authorized:false,canManage:false,showInNav:true});
  await page.goto('/?page=more');
  await expect(page.getByRole('button',{name:'Schwangerschaft & Baby',exact:true})).toHaveCount(0);
  await expect(page.locator('.bottom-nav').getByRole('button',{name:'Baby',exact:true})).toHaveCount(0);
});
