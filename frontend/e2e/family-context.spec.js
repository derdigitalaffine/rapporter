import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const familyOne={id:'family-1',name:'Musterfamilie',slug:'musterfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[{id:'member-1',family:'family-1',user:1,username:'alex',role:'owner',display_name:'Alex',avatar:''}]};
const familyTwo={id:'family-2',name:'Nebenfamilie',slug:'nebenfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[{id:'member-3',family:'family-2',user:1,username:'alex',role:'adult',display_name:'Alex',avatar:''}]};

function dashboardFor(familyId){
  if(familyId==='family-2')return {
    tasks:[{id:'task-b',family:'family-2',task_list:'tasks-b',title:'Hund füttern',notes:'',priority:'high',estimate_minutes:5,assignee:1,assignee_name:'Alex',list_name:'Nebenhaus',due_at:null,completed_at:null}],
    task_lists:[{id:'tasks-b',family:'family-2',name:'Nebenhaus',icon:'list-check',archived:false,sort_order:0,open_count:1,done_count:0}],
    events:[],routines:[],shopping_lists:[{id:'shop-b',family:'family-2',name:'Nebenhaus Einkauf',store:'',icon:'cart-shopping',archived:false,sort_order:0,items:[{id:'item-b',shopping_list:'shop-b',name:'Hundefutter',quantity:'1',category:'',aisle:'',note:'',favorite:false,checked:false}],open_count:1,checked_count:0}],inbox_count:0,automation_count:0,
  };
  return {
    tasks:[{id:'task-a',family:'family-1',task_list:'tasks-a',title:'Wäsche aufhängen',notes:'',priority:'normal',estimate_minutes:10,assignee:1,assignee_name:'Alex',list_name:'Alltag',due_at:null,completed_at:null}],
    task_lists:[{id:'tasks-a',family:'family-1',name:'Alltag',icon:'list-check',archived:false,sort_order:0,open_count:1,done_count:0}],
    events:[],routines:[],shopping_lists:[{id:'shop-a',family:'family-1',name:'Supermarkt',store:'',icon:'cart-shopping',archived:false,sort_order:0,items:[{id:'item-a',shopping_list:'shop-a',name:'Milch',quantity:'1 l',category:'',aisle:'',note:'',favorite:false,checked:false}],open_count:1,checked_count:0}],inbox_count:0,automation_count:0,
  };
}

async function setupTwoFamilies(page){
  await installApiMocks(page,{dismissOnboarding:true});
  await page.route('**/api/families/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([familyOne,familyTwo])}));
  await page.route('**/api/dashboard/**',route=>{
    const familyId=new URL(route.request().url()).searchParams.get('family')||'family-1';
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(dashboardFor(familyId))});
  });
}

test('family switcher isolates dashboard data and persists selection',async({page})=>{
  await setupTwoFamilies(page);
  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const switcher=page.locator('.family-switcher select');
  await expect(switcher).toHaveValue('family-1');
  await expect(page.getByText('Wäsche aufhängen',{exact:true})).toBeVisible();
  await expect(page.getByText('Hund füttern',{exact:true})).toHaveCount(0);

  await switcher.selectOption('family-2');
  await expect(switcher).toHaveValue('family-2');
  await expect(page.getByText('Hund füttern',{exact:true})).toBeVisible();
  await expect(page.getByText('Wäsche aufhängen',{exact:true})).toHaveCount(0);
  await expect(page.getByText('Hundefutter',{exact:true})).toBeVisible();
  await expect(page.getByText('Milch',{exact:true})).toHaveCount(0);

  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('.family-switcher select')).toHaveValue('family-2');
  await expect(page.getByText('Hund füttern',{exact:true})).toBeVisible();
  await expect(page.getByText('Wäsche aufhängen',{exact:true})).toHaveCount(0);
});
