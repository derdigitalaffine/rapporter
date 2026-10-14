import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const directEventProfile={
  ranking_version:1,
  cold_start_threshold:5,
  preferences:{smart_ranking_enabled:true,context_ranking_enabled:true,time_patterns_enabled:false,direct_mode:true,direct_action_id:'event',max_quick_actions:4,pinned_action_ids:[],hidden_action_ids:[],manual_order:[],learning_scope:'family'},
  stats:[],
};

async function routeDirectEventCreate(page){
  await page.route('**/api/create-actions/**',async route=>{
    if(route.request().method()==='POST')return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({...directEventProfile,accepted:true,deduplicated:false})});
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(directEventProfile)});
  });
}

async function pointHit(page,locator){
  const box=await locator.boundingBox();
  expect(box).not.toBeNull();
  const point={x:box.x+box.width/2,y:box.y+box.height/2};
  return {point,hit:await page.evaluate(({x,y})=>{
    const node=document.elementFromPoint(x,y);
    return {
      buttonClass:node?.closest('button')?.className||'',
      insideBottomNav:Boolean(node?.closest('.bottom-nav')),
      insideCreateControls:Boolean(node?.closest('.global-create-controls')),
      insideSheetBackdrop:Boolean(node?.closest('.sheet-backdrop')),
    };
  },point)};
}

test('global create stays clear of primary navigation across viewport offsets and breakpoints',async({page})=>{
  await installApiMocks(page,{dismissOnboarding:true});
  await routeDirectEventCreate(page);

  for(const viewport of [{width:390,height:844},{width:820,height:900}]){
    await page.setViewportSize(viewport);
    await page.goto('/?page=home');
    await page.waitForLoadState('networkidle');
    await page.evaluate(()=>document.documentElement.style.setProperty('--app-viewport-bottom','52px'));

    const nav=page.locator('.bottom-nav');
    const controls=page.locator('.global-create-controls');
    await expect(nav).toBeVisible();
    await expect(controls).toBeVisible();

    const navBox=await nav.boundingBox();
    const controlsBox=await controls.boundingBox();
    expect(navBox).not.toBeNull();
    expect(controlsBox).not.toBeNull();
    expect(controlsBox.y+controlsBox.height).toBeLessThanOrEqual(navBox.y-8);

    const navHit=await pointHit(page,nav.locator('button').first());
    expect(navHit.hit.insideBottomNav).toBe(true);
    expect(navHit.hit.insideCreateControls).toBe(false);

    const createHit=await pointHit(page,controls.locator('.global-create-fab'));
    expect(createHit.hit.insideCreateControls).toBe(true);
    expect(createHit.hit.insideBottomNav).toBe(false);

    const layers=await page.evaluate(()=>({
      navigation:Number(getComputedStyle(document.querySelector('.bottom-nav')).zIndex),
      create:Number(getComputedStyle(document.querySelector('.global-create-controls')).zIndex),
    }));
    expect(layers.navigation).toBeLessThan(layers.create);
  }
});

test('nested confirmation owns input above a modal sheet while app navigation stays inert',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  await routeDirectEventCreate(page);
  await page.goto('/?page=calendar');
  await page.waitForLoadState('networkidle');

  await page.locator('.calendar-mobile-daystrip').getByRole('button',{name:/Kinderarzt/}).click();
  await page.locator('.calendar-event-chip:visible').filter({hasText:'Kinderarzt'}).first().click();
  const detail=page.getByRole('dialog').filter({hasText:'Kinderarzt'});
  await detail.getByRole('button',{name:'Termin bearbeiten',exact:true}).click();

  const editor=page.getByRole('dialog',{name:'Termin bearbeiten'});
  await expect(editor).toBeVisible();

  const navButton=page.locator('.bottom-nav button').first();
  await expect(navButton).toBeVisible();
  const navHit=await pointHit(page,navButton);
  expect(navHit.hit.insideBottomNav).toBe(false);
  expect(navHit.hit.insideSheetBackdrop).toBe(true);

  await editor.locator('.ghost-danger.destructive-wide').click();
  const confirm=page.getByRole('alertdialog');
  await expect(confirm).toBeVisible();
  expect(await confirm.evaluate(node=>node.parentElement?.parentElement===document.body)).toBe(true);

  const layers=await page.evaluate(()=>{
    const nav=document.querySelector('.bottom-nav');
    const sheet=[...document.querySelectorAll('.sheet-backdrop')].find(node=>!node.classList.contains('confirm-backdrop'));
    const confirmBackdrop=document.querySelector('.confirm-backdrop');
    return {
      navigation:Number(getComputedStyle(nav).zIndex),
      sheet:Number(getComputedStyle(sheet).zIndex),
      dialog:Number(getComputedStyle(confirmBackdrop).zIndex),
    };
  });
  expect(layers.navigation).toBeLessThan(layers.sheet);
  expect(layers.sheet).toBeLessThan(layers.dialog);

  const confirmButton=confirm.locator('.destructive');
  const confirmHit=await pointHit(page,confirmButton);
  expect(confirmHit.hit.buttonClass).toContain('destructive');
  await page.mouse.click(confirmHit.point.x,confirmHit.point.y);
  await expect(confirm).toBeHidden();
  await expect(editor).toBeHidden();
});
