import {test,expect} from '@playwright/test';

const token='action-contract-token';
const invite={family_name:'Testfamilie',role:'adult',active:true,email_hint:'invite@example.test',display_name:'Alex'};

async function mockInvite(page){
 await page.route(`**/api/invite/${token}/`,route=>route.fulfill({json:invite}));
}

async function expectMinTarget(locator){
 const box=await locator.boundingBox();
 expect(box).not.toBeNull();
 expect(box.width).toBeGreaterThanOrEqual(44);
 expect(box.height).toBeGreaterThanOrEqual(44);
}

test('invite flow actions use explicit variants and button types on mobile',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.addInitScript(()=>{localStorage.removeItem('famuhle-session');localStorage.setItem('famuhle-language','de')});
 await mockInvite(page);
 await page.goto(`/invite/${token}/`);
 await expect(page.getByRole('heading',{name:'Testfamilie'})).toBeVisible();

 const register=page.getByRole('button',{name:'Neues Konto',exact:true});
 const login=page.getByRole('button',{name:'Schon registriert',exact:true});
 for(const action of [register,login]){
  await expect(action).toHaveAttribute('type','button');
  await expect(action).toHaveClass(/(^|\s)secondary(\s|$)/);
  await expect(action).toHaveClass(/(^|\s)compact(\s|$)/);
  await expectMinTarget(action);
 }
 await expect(register).toHaveAttribute('aria-pressed','true');
 await expect(login).toHaveAttribute('aria-pressed','false');

 const registerSubmit=page.getByRole('button',{name:'Konto erstellen & beitreten',exact:true});
 await expect(registerSubmit).toHaveAttribute('type','submit');
 await expect(registerSubmit).toHaveClass(/(^|\s)primary(\s|$)/);
 await expectMinTarget(registerSubmit);

 await login.click();
 await expect(register).toHaveAttribute('aria-pressed','false');
 await expect(login).toHaveAttribute('aria-pressed','true');
 const loginSubmit=page.getByRole('button',{name:'Anmelden & beitreten',exact:true});
 await expect(loginSubmit).toHaveAttribute('type','submit');
 await expect(loginSubmit).toHaveClass(/(^|\s)primary(\s|$)/);
 await expectMinTarget(loginSubmit);

 const language=page.getByRole('button',{name:/Deutsch \/ English/});
 await expect(language).toHaveAttribute('type','button');
 await expect(language).toHaveClass(/(^|\s)text-button(\s|$)/);
 await expectMinTarget(language);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>window.innerWidth));
});

test('authenticated invite accept keeps primary hierarchy with explicit action semantics',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.addInitScript(()=>{localStorage.setItem('famuhle-session','1');localStorage.setItem('famuhle-language','de')});
 await mockInvite(page);
 await page.goto(`/invite/${token}/`);
 await expect(page.getByRole('heading',{name:'Testfamilie'})).toBeVisible();
 const accept=page.getByRole('button',{name:'Familie beitreten',exact:true});
 await expect(accept).toHaveAttribute('type','button');
 await expect(accept).toHaveClass(/(^|\s)primary(\s|$)/);
 await expectMinTarget(accept);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(await page.evaluate(()=>window.innerWidth));
});
