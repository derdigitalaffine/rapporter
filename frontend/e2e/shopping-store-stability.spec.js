import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const now=()=>new Date().toISOString();
const session={
 id:'78078078-0780-4780-8780-780780780780',shopping_list:'shop-1',status:'active',started_at:now(),last_activity_at:now(),
 started_by:{id:1,name:'Alex',avatar:'',is_self:true},participants:[{id:1,name:'Alex',avatar:'',is_self:true},{id:2,name:'Sam',avatar:'S',is_self:false}],
};

function seedItems(state,count=24){
 state.shoppingLists[0].items=Array.from({length:count},(_,index)=>({
  id:`stability-${index}`,shopping_list:'shop-1',name:`Artikel ${index+1}`,quantity:'1×',category:`Bereich ${index%4+1}`,aisle:'',note:'',favorite:false,checked:false,position:(index+1)*1000,
 }));
}

async function openStore(page,{count=24,beforeGoto=null}={}){
 const state=await installApiMocks(page,{dismissOnboarding:true});
 seedItems(state,count);
 if(beforeGoto)await beforeGoto({page,state});
 await page.goto('/?page=shopping&list=shop-1&mode=store');
 await page.waitForLoadState('networkidle');
 await expect(page.locator('.store-focus')).toBeVisible();
 return state;
}

test.only('store · peer checks preserve personal filter, focus, scroll and ordering choice',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 let sessionPolls=0;let releaseRemote=false;let sentRemote=false;
 await openStore(page,{beforeGoto:async({page})=>{
  await page.route('**/api/shopping-sessions/start/',route=>route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({session,cursor:0,activities:[],created:true})}));
  await page.route('**/api/shopping-sessions/current/**',route=>{
   sessionPolls+=1;
   if(!releaseRemote||sentRemote)return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({session,cursor:sentRemote?1:0,activities:[]})});
   sentRemote=true;
   const item={id:'stability-0',shopping_list:'shop-1',name:'Artikel 1',quantity:'1×',category:'Bereich 1',aisle:'',note:'',favorite:false,checked:true,checked_at:now(),position:1000};
   const activity={sequence:1,kind:'item_checked',item_id:item.id,item_name:item.name,actor:{id:2,name:'Sam',avatar:'S',is_self:false},item,created_at:now()};
   return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({session,cursor:1,activities:[activity]})});
  });
 }});
 await expect(page.getByText('Einkauf läuft',{exact:true})).toBeVisible();
 await expect.poll(()=>sessionPolls,{timeout:6000}).toBeGreaterThanOrEqual(1);

 const allFilter=page.locator('.store-status-filter button').nth(2);
 await allFilter.click();
 await expect(allFilter).toHaveAttribute('aria-pressed','true');
 await expect(page.getByLabel('Sortierung im Laden')).toHaveValue('categories');
 await allFilter.focus();
 await expect(allFilter).toBeFocused();
 await page.evaluate(()=>window.scrollTo(0,520));
 const beforeScroll=await page.evaluate(()=>window.scrollY);
 expect(beforeScroll).toBeGreaterThan(200);

 const pollsBeforeRelease=sessionPolls;
 releaseRemote=true;
 await expect.poll(()=>sessionPolls,{timeout:6000}).toBeGreaterThan(pollsBeforeRelease);
 await expect(page.getByRole('button',{name:'1 im Wagen'})).toBeVisible();
 await expect(allFilter).toHaveAttribute('aria-pressed','true');
 await expect(allFilter).toBeFocused();
 await expect(page.getByLabel('Sortierung im Laden')).toHaveValue('categories');
 const afterScroll=await page.evaluate(()=>window.scrollY);
 expect(Math.abs(afterScroll-beforeScroll)).toBeLessThanOrEqual(2);
});

test.only('store · reduced motion removes row transitions and completion transform',async({page})=>{
 await page.emulateMedia({reducedMotion:'reduce'});
 await page.setViewportSize({width:390,height:844});
 await openStore(page,{count:8});
 const row=page.locator('.store-row').first();
 const styles=await row.evaluate(element=>{
  element.classList.add('store-completing');
  const style=getComputedStyle(element);
  const result={transitionDuration:style.transitionDuration,transform:style.transform};
  element.classList.remove('store-completing');
  return result;
 });
 const transitionSeconds=Math.max(...styles.transitionDuration.split(',').map(value=>Number.parseFloat(value.trim())||0));
 expect(transitionSeconds).toBeLessThanOrEqual(0.0001);
 expect(styles.transform).toBe('none');
});