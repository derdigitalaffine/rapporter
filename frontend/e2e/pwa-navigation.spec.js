import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function boot(page,{viewport={width:390,height:844},visualViewport=false}={}){
 await page.setViewportSize(viewport);
 await page.addInitScript(({visualViewport})=>{
  Object.defineProperty(navigator,'standalone',{configurable:true,value:true});
  if(visualViewport){
   const viewport=new EventTarget();
   Object.assign(viewport,{height:window.innerHeight,width:window.innerWidth,offsetTop:0,offsetLeft:0,scale:1});
   Object.defineProperty(window,'visualViewport',{configurable:true,value:viewport});
  }
 },{visualViewport});
 await installApiMocks(page);
 await page.goto('/');
 await expect(page.locator('.bottom-nav')).toBeVisible();
}

test('installed iOS PWA scrolls content without moving document, header or primary navigation',async({page},testInfo)=>{
 await boot(page);
 const content=page.locator('.app-shell>.content'),nav=page.locator('.bottom-nav');
 await content.evaluate(el=>{
  el.firstElementChild.style.minHeight='2200px';
  const tail=document.createElement('button');tail.textContent='Scroll end';tail.dataset.testScrollEnd='true';tail.style.minHeight='44px';el.append(tail);
 });
 const before=await nav.boundingBox(),header=await page.locator('.topbar').boundingBox();
 await content.evaluate(el=>el.scrollTo(0,900));
 await expect.poll(()=>content.evaluate(el=>el.scrollTop)).toBeGreaterThan(500);
 await page.evaluate(()=>window.scrollTo(0,900));
 expect(await page.evaluate(()=>window.scrollY)).toBe(0);
 expect((await nav.boundingBox()).y).toBeCloseTo(before.y,0);
 expect((await page.locator('.topbar').boundingBox()).y).toBeCloseTo(header.y,0);
 await content.evaluate(el=>el.scrollTop=el.scrollHeight);
 const tail=await page.locator('[data-test-scroll-end]').boundingBox();
 expect(tail.y+tail.height).toBeLessThanOrEqual(before.y);
 await content.hover();await page.mouse.wheel(0,1000);
 expect(await page.evaluate(()=>window.scrollY)).toBe(0);
 expect((await nav.boundingBox()).y).toBeCloseTo(before.y,0);
 await content.evaluate(el=>el.scrollTop=0);
 await page.mouse.wheel(0,-1000);
 expect(await page.evaluate(()=>window.scrollY)).toBe(0);
 await page.screenshot({path:testInfo.outputPath('standalone-navigation.png')});
});

test('elastic iOS viewport panning does not displace primary navigation',async({page})=>{
 await boot(page,{visualViewport:true});
 const nav=page.locator('.bottom-nav'),before=await nav.boundingBox();
 await page.evaluate(()=>{window.visualViewport.offsetTop=-40;window.visualViewport.dispatchEvent(new Event('scroll'))});
 await expect.poll(()=>nav.evaluate(el=>el.getBoundingClientRect().y)).toBeCloseTo(before.y,0);
 await expect.poll(()=>page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--app-viewport-top').trim())).toBe('0px');
 await page.evaluate(()=>{window.visualViewport.offsetTop=40;window.visualViewport.dispatchEvent(new Event('scroll'))});
 await expect.poll(()=>page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--app-viewport-top').trim())).toBe('0px');
 await expect(nav).toHaveCSS('transform','none');
});

test('transient iOS visual viewport changes do not lift app chrome',async({page})=>{
 await boot(page,{visualViewport:true});
 const nav=page.locator('.bottom-nav'),controls=page.locator('.global-create-controls');
 await expect(controls).toBeVisible();
 const beforeNav=await nav.boundingBox(),beforeControls=await controls.boundingBox();
 expect(beforeControls.y+beforeControls.height).toBeLessThanOrEqual(beforeNav.y);

 await page.evaluate(()=>{Object.assign(window.visualViewport,{height:784,offsetTop:0});window.visualViewport.dispatchEvent(new Event('resize'))});
 await expect.poll(()=>nav.evaluate(el=>el.getBoundingClientRect().bottom)).toBeCloseTo(844,0);
 await expect.poll(()=>page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--app-viewport-height').trim())).toBe('844px');
 const afterNav=await nav.boundingBox(),afterControls=await controls.boundingBox();
 expect(afterNav.y).toBeCloseTo(beforeNav.y,0);
 expect(afterControls.y).toBeCloseTo(beforeControls.y,0);
 expect(afterControls.y+afterControls.height).toBeLessThanOrEqual(afterNav.y);
});

for(const viewport of [{width:390,height:844},{width:844,height:390}])test(`standalone navigation and forms remain reachable at ${viewport.width}x${viewport.height}`,async({page})=>{
 await boot(page,{viewport});
 const nav=page.locator('.bottom-nav');
 await nav.getByRole('button',{name:'To-dos',exact:true}).click();
 await expect(page.locator('.todo-hub')).toBeVisible();
 await page.locator('.todo-capture > summary').click();
 const capture=page.locator('.todo-capture').getByRole('textbox',{name:'Ich habe gerade …',exact:true});
 await capture.fill('PWA task');
 await capture.blur();
 await nav.getByRole('button',{name:'Mehr',exact:true}).click();
 await expect(page).toHaveURL(/page=more/);
 await page.goBack();await expect(page.locator('.todo-hub')).toBeVisible();
 const box=await nav.boundingBox();expect(box.y+box.height).toBeCloseTo(viewport.height,0);
 expect(await page.evaluate(()=>window.scrollY)).toBe(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth-window.innerWidth)).toBeLessThanOrEqual(1);
 await page.locator('.global-create-fab').click();
 const dialog=page.getByRole('dialog');await expect(dialog).toBeVisible();
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);
});

test('standalone keyboard resize keeps editing usable without moving persistent navigation',async({page})=>{
 await boot(page,{visualViewport:true});
 await page.locator('.bottom-nav').getByRole('button',{name:'To-dos',exact:true}).click();
 await page.locator('.todo-capture > summary').click();
 const field=page.locator('.todo-capture').getByRole('textbox',{name:'Ich habe gerade …',exact:true});await field.focus();
 await page.evaluate(()=>{Object.assign(window.visualViewport,{height:440,offsetTop:0});window.visualViewport.dispatchEvent(new Event('resize'))});
 await expect.poll(()=>page.evaluate(()=>document.documentElement.hasAttribute('data-app-keyboard'))).toBe(true);
 await expect.poll(()=>page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--app-viewport-height').trim())).toBe('440px');
 await expect.poll(()=>page.locator('.bottom-nav').evaluate(el=>el.getBoundingClientRect().bottom)).toBeCloseTo(844,0);
 await field.fill('Keyboard stays usable');await expect(field).toHaveValue('Keyboard stays usable');
 // Synthetic viewport events do not perform the OS keyboard's native reveal.
 // Exercise the current scrolled capture field without moving app chrome.
 await field.evaluate(el=>el.scrollIntoView({block:'start',behavior:'instant'}));
 const box=await field.boundingBox();expect(box.y+box.height).toBeLessThanOrEqual(440);
 expect(await page.evaluate(()=>window.scrollY)).toBe(0);

 // Reproduce iOS dismissal race: focus is gone, but the final viewport resize
 // has not arrived yet. Stable chrome must recover immediately.
 await field.evaluate(el=>el.blur());
 await expect.poll(()=>page.evaluate(()=>document.documentElement.hasAttribute('data-app-keyboard'))).toBe(false);
 await expect.poll(()=>page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--app-viewport-height').trim())).toBe('844px');
 await expect.poll(()=>page.locator('.bottom-nav').evaluate(el=>el.getBoundingClientRect().bottom)).toBeCloseTo(844,0);

 await page.evaluate(()=>{Object.assign(window.visualViewport,{height:844,offsetTop:0});window.visualViewport.dispatchEvent(new Event('resize'))});
 await expect.poll(()=>page.locator('.bottom-nav').evaluate(el=>el.getBoundingClientRect().bottom)).toBeCloseTo(844,0);
});
