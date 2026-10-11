import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';
const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

async function expectMinTarget(locator){const box=await locator.boundingBox();expect(box?.width).toBeGreaterThanOrEqual(44);expect(box?.height).toBeGreaterThanOrEqual(44)}

test('owner sends targeted family message, clears unread state and keeps canonical inbox actions',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page);let messages=[{id:'system-1',family:'family-1',title:'Hinweis',body:'Fenster schließen',source:'automation',status:'new',created_by:null,created_by_name:'FamilyOS',audience:'family',important:false,withdrawn_at:null,recipients:[],unread:true,can_withdraw:false,created_at:'2026-10-09T12:00:00Z'}];
  await page.route('**/api/inbox/**',async route=>{const request=route.request();const url=new URL(request.url());const method=request.method();const path=url.pathname;if(path==='/api/inbox/'&&method==='GET')return json(route,messages);if(path==='/api/inbox/'&&method==='POST'){const body=request.postDataJSON();const created={id:'message-1',family:'family-1',title:body.body,body:body.body,source:'manual_message',status:'sent',created_by:1,created_by_name:'Alex',audience:body.audience,important:body.important,withdrawn_at:null,recipients:[{id:'member-2',display_name:'Sam',username:'sam'}],unread:false,can_withdraw:true,created_at:'2026-10-09T12:05:00Z'};messages=[created,...messages];return json(route,created,201)}if(path==='/api/inbox/system-1/read/'&&method==='POST'){messages=messages.map(item=>item.id==='system-1'?{...item,unread:false,status:'read'}:item);return json(route,messages.find(item=>item.id==='system-1'))}return json(route,{})});
  await page.goto('/?page=inbox');await page.waitForLoadState('networkidle');await expect(page.getByRole('heading',{name:'Mitteilungen'})).toBeVisible();await expect(page.getByText('Fenster schließen')).toBeVisible();

  const back=page.getByRole('button',{name:'Zurück'});await expect(back).toHaveClass(/\bghost\b/);await expect(back).toHaveClass(/\bicon-button\b/);await expectMinTarget(back);
  const create=page.getByRole('button',{name:/Mitteilung$/});await expect(create).toHaveClass(/\bprimary\b/);await expect(create).toHaveAttribute('aria-expanded','false');await expectMinTarget(create);
  const allFilter=page.getByRole('button',{name:'Alle'});const unreadFilter=page.getByRole('button',{name:'Ungelesen'});await expect(allFilter).toHaveAttribute('aria-pressed','true');await expect(unreadFilter).toHaveAttribute('aria-pressed','false');
  const systemActions=page.locator('#family-message-system-1 .family-message-actions button');await expect(systemActions).toHaveCount(3);for(let index=0;index<3;index++){await expect(systemActions.nth(index)).toHaveClass(/\bsecondary\b/);await expectMinTarget(systemActions.nth(index))}
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  await create.click();await expect(create).toHaveAttribute('aria-expanded','true');const compose=page.locator('#family-message-compose');await expect(compose.getByRole('button',{name:'Abbrechen'})).toHaveClass(/\bsecondary\b/);await expect(compose.getByRole('button',{name:'Senden'})).toHaveClass(/\bprimary\b/);await page.getByRole('textbox',{name:'Mitteilung',exact:true}).fill('Bitte Milch mitbringen');await page.getByLabel('Empfänger').selectOption('selected');await page.getByText('Sam',{exact:true}).click();await page.getByLabel('Wichtig / anpinnen').check();await page.getByRole('button',{name:'Senden',exact:true}).click();await expect(page.getByText('Bitte Milch mitbringen')).toBeVisible();await expect(page.getByText('An Sam')).toBeVisible();await expect(page.getByText('Wichtig',{exact:true})).toBeVisible();

  const withdraw=page.locator('#family-message-message-1').getByRole('button',{name:'Zurückziehen'});await expect(withdraw).toHaveClass(/\bghost\b/);await expect(withdraw).toHaveClass(/\bghost-danger\b/);await expectMinTarget(withdraw);
  await unreadFilter.click();await expect(unreadFilter).toHaveAttribute('aria-pressed','true');await expect(allFilter).toHaveAttribute('aria-pressed','false');await expect(page.getByText('Fenster schließen')).toBeVisible();await page.getByText('Fenster schließen').click();await expect(page.getByText('Fenster schließen')).toHaveCount(0);

  await page.setViewportSize({width:1440,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  await page.goto('/?page=inbox&message=message-1');await page.waitForLoadState('networkidle');await expect(page.getByRole('heading',{name:'Mitteilungen'})).toBeVisible();await expect(page.locator('#family-message-message-1')).toHaveAttribute('data-focused','true');await expect(page.getByRole('dialog')).toHaveCount(0);
});
