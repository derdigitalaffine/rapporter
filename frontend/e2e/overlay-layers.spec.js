import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const createProfile=({direct=false,action='' }={})=>({
  ranking_version:1,
  cold_start_threshold:5,
  preferences:{smart_ranking_enabled:true,context_ranking_enabled:true,time_patterns_enabled:false,direct_mode:direct,direct_action_id:action,max_quick_actions:4,pinned_action_ids:[],hidden_action_ids:[],manual_order:[],learning_scope:'family'},
  stats:[],
});

async function routeCreateProfile(page,profile=createProfile()){
  await page.route('**/api/create-actions/**',async route=>{
    if(route.request().method()==='POST')return route.fulfill({status:201,contentType:'application/json',body:JSON.stringify({...profile,accepted:true,deduplicated:false})});
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(profile)});
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

test('global create stays clear of primary navigation despite stale viewport inset',async({page})=>{
  await installApiMocks(page,{dismissOnboarding:true});
  await routeCreateProfile(page,createProfile({direct:true,action:'event'}));

  for(const viewport of [{width:390,height:844},{width:820,height:900}]){
    await page.setViewportSize(viewport);
    await page.goto('/?page=home');
    await page.waitForLoadState('networkidle');

    const nav=page.locator('.bottom-nav');
    const controls=page.locator('.global-create-controls');
    await expect(nav).toBeVisible();
    await expect(controls).toBeVisible();
    const stableNav=await nav.boundingBox();
    const stableControls=await controls.boundingBox();

    await page.evaluate(()=>document.documentElement.style.setProperty('--app-viewport-bottom','52px'));
    const navBox=await nav.boundingBox();
    const controlsBox=await controls.boundingBox();
    expect(navBox.y).toBeCloseTo(stableNav.y,0);
    expect(controlsBox.y).toBeCloseTo(stableControls.y,0);
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

test('nested confirmation owns input above a modal sheet while app chrome is hidden',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  await routeCreateProfile(page,createProfile({direct:true,action:'event'}));
  await page.goto('/?page=calendar');
  await page.waitForLoadState('networkidle');

  await page.locator('.calendar-mobile-daystrip').getByRole('button',{name:/Kinderarzt/}).click();
  await page.locator('.calendar-event-chip:visible').filter({hasText:'Kinderarzt'}).first().click();
  const detail=page.getByRole('dialog').filter({hasText:'Kinderarzt'});
  await detail.getByRole('button',{name:'Termin bearbeiten',exact:true}).click();

  const editor=page.getByRole('dialog',{name:'Termin bearbeiten'});
  await expect(editor).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-app-modal','');
  await expect(page.locator('.bottom-nav')).toBeHidden();
  await expect(page.locator('.global-create-controls')).toBeHidden();

  await editor.locator('.ghost-danger.destructive-wide').click();
  const confirm=page.getByRole('alertdialog');
  await expect(confirm).toBeVisible();
  expect(await confirm.evaluate(node=>node.parentElement?.parentElement===document.body)).toBe(true);

  const layers=await page.evaluate(()=>{
    const sheet=[...document.querySelectorAll('.sheet-backdrop')].find(node=>!node.classList.contains('confirm-backdrop'));
    const confirmBackdrop=document.querySelector('.confirm-backdrop');
    return {
      sheet:Number(getComputedStyle(sheet).zIndex),
      dialog:Number(getComputedStyle(confirmBackdrop).zIndex),
    };
  });
  expect(layers.sheet).toBeLessThan(layers.dialog);

  const confirmButton=confirm.locator('.destructive');
  const confirmHit=await pointHit(page,confirmButton);
  expect(confirmHit.hit.buttonClass).toContain('destructive');
  await page.mouse.click(confirmHit.point.x,confirmHit.point.y);
  await expect(confirm).toBeHidden();
  await expect(editor).toBeHidden();
  await expect(page.locator('html')).not.toHaveAttribute('data-app-modal','');
  await expect(page.locator('.bottom-nav')).toBeVisible();
});

test('task editor is a root modal and permanent chrome never competes with its actions',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  await routeCreateProfile(page);
  await page.goto('/?page=tasks');
  await page.waitForLoadState('networkidle');

  await page.locator('.global-create-fab').click();
  const palette=page.getByRole('dialog',{name:'Neu hinzufügen'});
  await expect(palette).toBeVisible();
  await palette.getByRole('button',{name:/Aufgabe/}).first().click();

  const editor=page.getByRole('dialog').filter({has:page.getByRole('heading',{name:'Aufgabe hinzufügen'})});
  await expect(editor).toBeVisible();
  expect(await editor.evaluate(node=>node.parentElement?.parentElement===document.body)).toBe(true);
  await expect(page.locator('html')).toHaveAttribute('data-app-modal','');
  await expect(page.locator('.bottom-nav')).toBeHidden();
  await expect(page.locator('.global-create-controls')).toBeHidden();

  const save=editor.getByRole('button',{name:'Speichern',exact:true});
  await editor.getByLabel('Titel').fill('Layer-Vertrag prüfen');
  const saveHit=await pointHit(page,save);
  expect(saveHit.hit.buttonClass).toContain('primary');
  expect(saveHit.hit.insideBottomNav).toBe(false);
});

test('keyboard resizes only the modal surface, never permanent app chrome',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  await routeCreateProfile(page);
  await page.goto('/?page=tasks');
  await page.waitForLoadState('networkidle');

  await page.locator('.global-create-fab').click();
  const palette=page.getByRole('dialog',{name:'Neu hinzufügen'});
  await palette.getByRole('button',{name:/Aufgabe/}).first().click();
  const editor=page.getByRole('dialog').filter({has:page.getByRole('heading',{name:'Aufgabe hinzufügen'})});
  await expect(editor).toBeVisible();

  await page.evaluate(()=>{
    const root=document.documentElement;
    root.setAttribute('data-app-standalone','');
    root.setAttribute('data-app-keyboard','');
    root.style.setProperty('--app-viewport-top','44px');
    root.style.setProperty('--app-viewport-height','480px');
  });

  const geometry=await page.evaluate(()=>{
    const backdrop=document.querySelector('body > .sheet-backdrop');
    const shell=document.querySelector('.app-shell:not(.messenger-shell)');
    const b=backdrop.getBoundingClientRect();
    const s=shell.getBoundingClientRect();
    return {backdrop:{top:b.top,height:b.height,bottom:b.bottom},shell:{top:s.top,height:s.height,bottom:s.bottom}};
  });
  expect(geometry.backdrop.top).toBeCloseTo(44,0);
  expect(geometry.backdrop.height).toBeCloseTo(480,0);
  expect(geometry.backdrop.bottom).toBeCloseTo(524,0);
  expect(geometry.shell.height).toBeCloseTo(844,0);
  await expect(page.locator('.bottom-nav')).toBeHidden();
  await expect(page.locator('.global-create-controls')).toBeHidden();

  const title=editor.getByLabel('Titel');
  await title.fill('Tastatur ohne Abdeck-Layer');
  await expect(title).toBeVisible();

  await page.evaluate(()=>{
    const root=document.documentElement;
    root.removeAttribute('data-app-keyboard');
    root.style.setProperty('--app-viewport-top','0px');
    root.style.setProperty('--app-viewport-height','844px');
  });
  const fullBackdrop=await page.locator('body > .sheet-backdrop').boundingBox();
  expect(fullBackdrop.y).toBeCloseTo(0,0);
  expect(fullBackdrop.height).toBeCloseTo(844,0);
  await expect(page.locator('.bottom-nav')).toBeHidden();
});
