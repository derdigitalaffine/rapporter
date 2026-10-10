import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';


test('visible signed-in PWA clears and acknowledges unread launcher badge',async({page})=>{
 await page.addInitScript(()=>{
  window.__badgeCalls=[];
  Object.defineProperty(navigator,'clearAppBadge',{configurable:true,value:async()=>{window.__badgeCalls.push(['clear'])}});
  Object.defineProperty(navigator,'setAppBadge',{configurable:true,value:async count=>{window.__badgeCalls.push(['set',count])}});
 });
 await installApiMocks(page,{dismissOnboarding:true});
 let acknowledgements=0;
 await page.route('**/api/push/badge/**',route=>{
  if(route.request().method()==='POST')acknowledgements+=1;
  return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({unread_count:0})});
 });
 await page.goto('/');
 await expect.poll(()=>acknowledgements).toBeGreaterThan(0);
 await expect.poll(()=>page.evaluate(()=>window.__badgeCalls.some(call=>call[0]==='clear'))).toBe(true);
});

test('deployed service worker applies numeric badge through WorkerNavigator',async({request})=>{
 const response=await request.get('/sw.js');
 expect(response.ok()).toBe(true);
 const source=await response.text();
 expect(source).toContain('self.navigator.setAppBadge(value)');
 expect(source).toContain('self.navigator.clearAppBadge()');
 expect(source).toContain('data.badge_count');
 expect(source).toContain("type:'FAMILYOS_BADGE'");
});
