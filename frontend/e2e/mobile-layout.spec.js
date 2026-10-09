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

  await page.getByRole('button',{name:/^(Aufgaben|Tasks)$/}).click();
  await expect(page.locator('.smart-input input')).toBeVisible();
  await expect(page.locator('.smart-input input')).toHaveCSS('font-size','16px');
  await assertNoHorizontalOverflow(page);
});

for(const viewport of [{width:390,height:844},{width:428,height:926}]){
  test(`iPhone portrait ${viewport.width}x${viewport.height} keeps Today content inside the viewport`,async({page})=>{
    await boot(page,viewport,{emptyTasks:true});

    await expect(page.locator('.today-page')).toBeVisible();
    await expect(page.locator('.today-quick-actions button')).toHaveCount(3);
    await assertNoHorizontalOverflow(page);
    await assertInsideViewport(page,page.locator('.today-quick-actions'));

    for(const button of await page.locator('.today-quick-actions button').all()){
      await assertInsideViewport(page,button);
    }

    const emptyState=page.locator('.today-calm');
    await expect(emptyState).toBeVisible();
    await assertInsideViewport(page,emptyState);
    await assertInsideViewport(page,page.locator('.today-empty-action'));
  });
}

for(const viewport of [{width:844,height:390},{width:926,height:428}]){
  test(`iPhone landscape ${viewport.width}x${viewport.height} uses compact bottom navigation`,async({page})=>{
    await boot(page,viewport);

    await assertNoHorizontalOverflow(page);
    const nav=page.locator('.bottom-nav');
    await expect(nav).toBeVisible();
    const navBox=await nav.boundingBox();
    expect(navBox).not.toBeNull();
    expect(navBox.height).toBeLessThanOrEqual(90);
    expect(navBox.y).toBeGreaterThan(viewport.height-100);
    expect(navBox.y+navBox.height).toBeLessThanOrEqual(viewport.height+0.5);
    await assertInsideViewport(page,nav);

    const first=await nav.locator('button').nth(0).boundingBox();
    const second=await nav.locator('button').nth(1).boundingBox();
    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
    expect(Math.abs(first.y-second.y)).toBeLessThanOrEqual(1);
    expect(second.x).toBeGreaterThan(first.x);

    const layout=await nav.evaluate(element=>{
      const style=getComputedStyle(element);
      return {position:style.position,bottom:style.bottom,columns:style.gridTemplateColumns.split(' ').filter(Boolean).length};
    });
    expect(layout.position).toBe('fixed');
    expect(layout.bottom).toBe('0px');
    expect(layout.columns).toBe(5);

    await assertInsideViewport(page,page.locator('.today-quick-actions'));
  });
}
