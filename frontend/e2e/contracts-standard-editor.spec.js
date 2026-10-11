import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

const contract={
  id:'contract-1',
  family:'family-1',
  title:'Internetvertrag',
  category:'Internet',
  provider:'MusterNet',
  contract_number:'V-12345',
  customer_number:'K-98765',
  start_date:'2026-01-01',
  minimum_term_months:24,
  end_date:'2027-12-31',
  cancellation_period:'3 Monate',
  renewal_rule:'12 Monate',
  amount:'39.90',
  billing_interval:'monthly',
  status:'active',
  notes:'Router inklusive',
  visibility:'private',
  documents:[],
  derived_dates:[
    {key:'minimum_term_end',date:'2027-12-31'},
    {key:'cancellation_deadline',date:'2027-09-30'},
  ],
};

async function mockContracts(page,onPatch=()=>{}){
  await page.route('**/api/contracts/**',async route=>{
    const request=route.request();
    const url=new URL(request.url());
    const method=request.method();
    if(url.pathname==='/api/contracts/'&&method==='GET')return json(route,[contract]);
    if(url.pathname==='/api/contracts/contract-1/'&&method==='PATCH'){
      const payload=request.postDataJSON();onPatch(payload);return json(route,{...contract,...payload});
    }
    return route.fallback();
  });
}

test('contract editor groups primary fields and preserves progressive details',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page);
  let patchPayload=null;
  await mockContracts(page,payload=>{patchPayload=payload});

  await page.goto('/?page=contracts&family=family-1');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button',{name:/Internetvertrag/}).click();

  const dialog=page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('group',{name:'Vertrag'})).toBeVisible();
  await expect(dialog.getByRole('group',{name:'Laufzeit'})).toBeVisible();
  await expect(dialog.getByRole('group',{name:'Kosten'})).toBeVisible();
  await expect(dialog.getByRole('group',{name:'Freigabe'})).toBeVisible();

  const details=dialog.getByRole('button',{name:/Weitere Details/});
  await expect(details).toHaveAttribute('aria-expanded','false');
  await expect(dialog.getByLabel('Vertragsnummer')).toHaveCount(0);

  await details.focus();
  await page.keyboard.press('Enter');
  await expect(details).toHaveAttribute('aria-expanded','true');
  await expect(dialog.getByLabel('Vertragsnummer')).toHaveValue('V-12345');
  await expect(dialog.getByLabel('Kundennummer')).toHaveValue('K-98765');
  await expect(dialog.getByLabel('Notizen')).toHaveValue('Router inklusive');

  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  await page.setViewportSize({width:320,height:720});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  await details.click();
  for(const viewport of [{width:1024,height:768},{width:1440,height:900},{width:720,height:450}]){
    await page.setViewportSize(viewport);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  }
  await dialog.getByRole('button',{name:'Speichern'}).click();
  await expect.poll(()=>patchPayload).not.toBeNull();
  expect(patchPayload).toMatchObject({
    title:'Internetvertrag',
    provider:'MusterNet',
    contract_number:'V-12345',
    customer_number:'K-98765',
    renewal_rule:'12 Monate',
    status:'active',
    notes:'Router inklusive',
    visibility:'private',
  });
});

for(const [language,labels] of Object.entries({
  en:['Contract','Term','Costs','More details','Sharing'],
  fr:['Contrat','Durée','Coûts','Plus de détails','Partage'],
  nl:['Contract','Looptijd','Kosten','Meer details','Delen'],
  th:['สัญญา','ระยะสัญญา','ค่าใช้จ่าย','รายละเอียดเพิ่มเติม','การแชร์'],
})){
  test(`contract StandardEditor labels are localized in ${language}`,async({page})=>{
    await installApiMocks(page,{language});
    await mockContracts(page);
    await page.goto('/?page=contracts&family=family-1');
    await page.waitForLoadState('networkidle');
    await page.getByRole('button',{name:/Internetvertrag/}).click();
    const dialog=page.getByRole('dialog');
    await expect(dialog.getByRole('group',{name:labels[0],exact:true})).toBeVisible();
    await expect(dialog.getByRole('group',{name:labels[1],exact:true})).toBeVisible();
    await expect(dialog.getByRole('group',{name:labels[2],exact:true})).toBeVisible();
    await expect(dialog.getByRole('button',{name:new RegExp(labels[3])})).toBeVisible();
    await expect(dialog.getByRole('group',{name:labels[4],exact:true})).toBeVisible();
  });
}

test('contract validation focuses the summary and server errors retain edits',async({page})=>{
  await installApiMocks(page,{dismissOnboarding:true});
  await mockContracts(page);
  await page.goto('/?page=contracts&family=family-1');
  await page.getByRole('button',{name:/Internetvertrag/}).click();
  const dialog=page.getByRole('dialog');
  const title=dialog.getByLabel('Bezeichnung');
  await title.fill('');
  await dialog.getByRole('button',{name:'Speichern'}).click();
  const summary=dialog.locator('.error-summary');
  await expect(summary).toBeFocused();
  await expect(title).toHaveAttribute('aria-invalid','true');
  await summary.getByRole('link').click();
  await expect(title).toBeFocused();
  await title.fill('Überarbeiteter Vertrag');
  await page.route('**/api/contracts/contract-1/',route=>json(route,{detail:'Temporarily unavailable'},503));
  await dialog.getByRole('button',{name:'Speichern'}).click();
  await expect(dialog.getByRole('alert')).toContainText('Temporarily unavailable');
  await expect(title).toHaveValue('Überarbeiteter Vertrag');
  await expect(dialog.getByRole('button',{name:'Speichern'})).toBeEnabled();
});
