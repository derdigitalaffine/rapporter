import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const primaryFamily={id:'family-1',name:'Musterfamilie',slug:'musterfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[]};
const secondFamily={id:'family-2',name:'Sehr lange Nebenfamilie mit langem Namen',slug:'nebenfamilie',locale:'de',timezone:'Europe/Berlin',memberships:[]};

async function assertNoHorizontalOverflow(page){
  const metrics=await page.evaluate(()=>({
    viewport:window.innerWidth,
    html:document.documentElement.scrollWidth,
    body:document.body.scrollWidth,
    root:document.getElementById('root')?.scrollWidth||0,
  }));
  expect(metrics.html).toBeLessThanOrEqual(metrics.viewport);
  expect(metrics.body).toBeLessThanOrEqual(metrics.viewport);
  expect(metrics.root).toBeLessThanOrEqual(metrics.viewport);
}

async function assertInsideViewport(page,locator){
  const box=await locator.boundingBox();
  expect(box).not.toBeNull();
  const viewport=page.viewportSize();
  expect(box.x).toBeGreaterThanOrEqual(-0.5);
  expect(box.x+box.width).toBeLessThanOrEqual(viewport.width+0.5);
}

async function assertPrimaryNavigation(page,{compact}){
  const nav=page.locator('.bottom-nav');
  await expect(nav).toBeVisible();
  await expect(nav.locator('button')).toHaveCount(5);
  await expect(nav.getByRole('button',{name:/^(Heute|Today)$/})).toBeVisible();
  await expect(nav.getByRole('button',{name:/^(Aufgaben|Tasks)$/})).toBeVisible();
  await expect(nav.getByRole('button',{name:/^(Einkauf|Shopping)$/})).toBeVisible();
  await expect(nav.getByRole('button',{name:/^(Kalender|Calendar)$/})).toBeVisible();
  await expect(nav.getByRole('button',{name:/^(Mehr|More)$/})).toBeVisible();
  const layout=await nav.evaluate(element=>{const style=getComputedStyle(element);return{position:style.position,bottom:style.bottom,columns:style.gridTemplateColumns.split(' ').filter(Boolean).length}});
  expect(layout.position).toBe('fixed');
  if(compact){expect(layout.bottom).toBe('0px');expect(layout.columns).toBe(5)}else{expect(layout.columns).toBe(1)}
}

async function boot(page,viewport,{emptyTasks=false}={}){
  await page.setViewportSize(viewport);
  await installApiMocks(page,{dismissOnboarding:true});
  await page.route('**/api/families/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify([primaryFamily,secondFamily])}));
  if(emptyTasks){
    await page.route('**/api/dashboard/**',route=>route.fulfill({
      status:200,
      contentType:'application/json',
      body:JSON.stringify({tasks:[],task_lists:[],events:[],routines:[],shopping_lists:[],inbox_count:0,automation_count:0}),
    }));
  }
  await page.goto('/');
  await page.waitForLoadState('networkidle');
}

test('narrow iPhone-sized viewport does not overflow and form controls stay at 16px',async({page})=>{
  await boot(page,{width:320,height:568});
  const familySelect=page.locator('.family-switcher select');
  await expect(familySelect).toBeVisible();
  await expect(familySelect).toHaveCSS('font-size','16px');
  await assertNoHorizontalOverflow(page);
  await assertPrimaryNavigation(page,{compact:true});
  await page.getByRole('button',{name:/^(Aufgaben|Tasks)$/}).click();
  await expect(page.locator('.smart-input input')).toBeVisible();
  await expect(page.locator('.smart-input input')).toHaveCSS('font-size','16px');
  await assertNoHorizontalOverflow(page);
});

for(const viewport of [{width:360,height:800},{width:390,height:844},{width:428,height:926}]){
  test(`phone portrait ${viewport.width}x${viewport.height} keeps Today content inside the viewport`,async({page})=>{
    await boot(page,viewport,{emptyTasks:true});
    await expect(page.locator('.today-page')).toBeVisible();
    await expect(page.locator('.today-quick-actions button')).toHaveCount(3);
    await assertNoHorizontalOverflow(page);
    await assertPrimaryNavigation(page,{compact:true});
    await assertInsideViewport(page,page.locator('.today-quick-actions'));
    for(const button of await page.locator('.today-quick-actions button').all())await assertInsideViewport(page,button);
    const emptyState=page.locator('.today-calm');
    await expect(emptyState).toBeVisible();
    await assertInsideViewport(page,emptyState);
    await assertInsideViewport(page,page.locator('.today-empty-action'));
  });
}

for(const viewport of [{width:844,height:390},{width:926,height:428}]){
  test(`phone landscape ${viewport.width}x${viewport.height} stays compact`,async({page})=>{
    await boot(page,viewport);
    await assertNoHorizontalOverflow(page);
    await assertPrimaryNavigation(page,{compact:true});
    const nav=page.locator('.bottom-nav');
    const navBox=await nav.boundingBox();
    expect(navBox.height).toBeLessThanOrEqual(90);
    expect(navBox.y).toBeGreaterThan(viewport.height-100);
    expect(navBox.y+navBox.height).toBeLessThanOrEqual(viewport.height+0.5);
    await assertInsideViewport(page,nav);
    const first=await nav.locator('button').nth(0).boundingBox();
    const second=await nav.locator('button').nth(1).boundingBox();
    expect(Math.abs(first.y-second.y)).toBeLessThanOrEqual(1);
    expect(second.x).toBeGreaterThan(first.x);
    await assertInsideViewport(page,page.locator('.today-quick-actions'));
  });
}

for(const viewport of [{width:768,height:1024},{width:1024,height:768},{width:1180,height:820},{width:1280,height:800},{width:1440,height:900},{width:1920,height:1080}]){
  test(`adaptive layout ${viewport.width}x${viewport.height} uses bounded content and sidebar`,async({page})=>{
    await boot(page,viewport);
    await assertNoHorizontalOverflow(page);
    await assertPrimaryNavigation(page,{compact:false});
    const content=page.locator('.content');
    await assertInsideViewport(page,content);
    const contentBox=await content.boundingBox();
    expect(contentBox.width).toBeLessThanOrEqual(1321);
    const navBox=await page.locator('.bottom-nav').boundingBox();
    expect(navBox.x+navBox.width).toBeLessThanOrEqual(contentBox.x+1);
    const fab=page.locator('.global-create-fab');
    await expect(fab).toBeVisible();
    await assertInsideViewport(page,fab);
  });
}

test('tablet landscape keeps core navigation and create flow reachable',async({page})=>{
  await boot(page,{width:1024,height:768});
  for(const name of [/^(Aufgaben|Tasks)$/,/^(Kalender|Calendar)$/,/^(Mehr|More)$/,/^(Heute|Today)$/]){
    await page.locator('.bottom-nav').getByRole('button',{name}).click();
    await assertNoHorizontalOverflow(page);
  }
  await page.locator('.global-create-fab').click();
  await expect(page.locator('.quick-sheet')).toBeVisible();
  const sheet=await page.locator('.quick-sheet').boundingBox();
  expect(sheet.y).toBeGreaterThanOrEqual(0);
  expect(sheet.y+sheet.height).toBeLessThanOrEqual(768);
});

test('desktop navigation remains keyboard reachable at 1440x900',async({page})=>{
  await boot(page,{width:1440,height:900});
  const nav=page.locator('.bottom-nav');
  await nav.getByRole('button',{name:/^(Heute|Today)$/}).focus();
  await page.keyboard.press('Tab');
  await expect(nav.getByRole('button',{name:/^(Aufgaben|Tasks)$/})).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(nav.getByRole('button',{name:/^(Einkauf|Shopping)$/})).toBeFocused();
});
