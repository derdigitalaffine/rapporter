import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

async function installExpensesActionMocks(page){
  const ledger={id:'ledger-default',family:'family-1',name:'Familie – laufend',base_currency:'EUR',budget_amount:'500.00',is_default:true,archived:false};
  const expense={id:'expense-1',family:'family-1',ledger:'ledger-default',title:'Supermarkt',merchant:'Supermarkt',occurred_at:'2026-10-09T12:00:00.000Z',total_amount:'24.80',currency:'EUR',funding_source:'member',paid_by:'member-1',paid_by_name:'Alex',receipt_available:false,status:'posted',shares:[{id:'share-1',member:'member-1',member_name:'Alex',amount:'12.40'},{id:'share-2',member:'member-2',member_name:'Sam',amount:'12.40'}]};
  const settlement={id:'settlement-1',family:'family-1',ledger:'ledger-default',currency:'EUR',from_member:'member-2',from_name:'Sam',to_member:'member-1',to_name:'Alex',amount:'12.40',settled_at:'2026-10-09T13:00:00.000Z',voided_at:null};
  await page.route(/\/api\/(?:expense-ledgers|expenses)(?:\/.*)?(?:\?.*)?$/,async route=>{
    const request=route.request();const url=new URL(request.url());const path=url.pathname;
    if(path==='/api/expense-ledgers/'&&request.method()==='GET')return json(route,[ledger]);
    if(path==='/api/expense-ledgers/ledger-default/budget-summary/'&&request.method()==='GET')return json(route,{ledger:'ledger-default',currency:'EUR',budget_amount:'500.00',spent_amount:'24.80',remaining_amount:'475.20',over_budget:false,budgets:[],unconverted_expense_count:0});
    if(path==='/api/expenses/'&&request.method()==='GET')return json(route,[expense]);
    if(path==='/api/expenses/balance/'&&request.method()==='GET')return json(route,{family:'family-1',ledger:'ledger-default',currency:'EUR',open_amount:'12.40',members:[{id:'member-1',name:'Alex',balance:'12.40'},{id:'member-2',name:'Sam',balance:'-12.40'}]});
    if(path==='/api/expenses/settlement-plan/'&&request.method()==='GET')return json(route,{family:'family-1',ledger:'ledger-default',currency:'EUR',transfers:[{from_member:'member-2',from_name:'Sam',to_member:'member-1',to_name:'Alex',amount:'12.40'}]});
    if(path==='/api/expenses/settlements/'&&request.method()==='GET')return json(route,[settlement]);
    return route.fallback();
  });
}

async function expectMinTarget(locator){
  const box=await locator.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);
}

test('expenses hub uses canonical action hierarchy on mobile and desktop',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  await installExpensesActionMocks(page);
  await page.goto('/?page=expenses');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading',{name:'Geld & Finanzen',exact:true})).toBeVisible();
  await expect(page.getByText('Supermarkt',{exact:true})).toBeVisible();

  const back=page.locator('.expenses-back');
  await expect(back).toHaveClass(/\bghost\b/);
  await expect(back).toHaveClass(/\bicon-button\b/);
  await expect(back).toHaveAttribute('aria-label',/.+/);
  await expectMinTarget(back);

  const add=page.locator('.expenses-toolbar .primary');
  await expect(add).toHaveClass(/\bprimary\b/);
  await expectMinTarget(add);

  const edit=page.locator('.expense-actions').getByRole('button',{name:/Bearbeiten|Edit/i});
  await expect(edit).toHaveClass(/\bghost\b/);
  await expect(edit).toHaveClass(/\bicon-button\b/);
  await expect(edit).not.toHaveClass(/\bghost-danger\b/);
  await expectMinTarget(edit);

  const remove=page.locator('.expense-actions').getByRole('button',{name:/Löschen|Delete/i});
  await expect(remove).toHaveClass(/\bghost\b/);
  await expect(remove).toHaveClass(/\bicon-button\b/);
  await expect(remove).toHaveClass(/\bghost-danger\b/);
  await expectMinTarget(remove);

  const repayment=page.getByRole('button',{name:/Rückzahlung planen|Plan repayment/i});
  await expect(repayment).toHaveClass(/\bsecondary\b/);
  await expectMinTarget(repayment);
  const settle=page.getByRole('button',{name:/Als abgerechnet markieren|Mark as settled/i});
  await expect(settle).toHaveClass(/\bprimary\b/);
  await expectMinTarget(settle);
  const history=page.locator('.finance-history-card');
  await expect(history).not.toHaveAttribute('open','');
  await history.locator('summary').click();
  await expect(history).toHaveAttribute('open','');
  const undo=history.getByRole('button',{name:/Abrechnung stornieren|Void settlement/i});
  await expect(undo).toHaveClass(/\btext-button\b/);

  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
  for(const viewport of [{width:320,height:568},{width:1024,height:768},{width:1440,height:900}]){
    await page.setViewportSize(viewport);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    await expectMinTarget(back);
    await expectMinTarget(edit);
    await expectMinTarget(remove);
  }
  await remove.focus();
  await expect(remove).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('alertdialog')).toBeVisible();
});

test('repayment planning creates cent-accurate installment tasks for the debtor without settling',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page,{dismissOnboarding:true});
  await installExpensesActionMocks(page);
  const taskRequests=[];let settlementPosts=0;
  await page.route('**/api/tasks/',async route=>{
    if(route.request().method()!=='POST')return route.fallback();
    const body=route.request().postDataJSON();taskRequests.push(body);
    return json(route,{id:`repayment-${taskRequests.length}`,...body,completed_at:null},201);
  });
  await page.route('**/api/expenses/settlements/',async route=>{
    if(route.request().method()==='POST'){settlementPosts+=1;return json(route,{id:'unexpected'},201)}
    return route.fallback();
  });

  await page.goto('/?page=expenses');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button',{name:/Rückzahlung planen|Plan repayment/i}).click();
  const dialog=page.getByRole('dialog',{name:/Rückzahlung planen|Plan repayment/i});
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button',{name:/Ratenzahlung|Installments/i}).click();
  const count=dialog.getByLabel(/Anzahl Raten|Number of installments/i);
  await count.fill('3');

  await expect(dialog.getByText(/4,14\s?€|€4\.14/)).toBeVisible();
  await expect(dialog.getByText(/4,13\s?€|€4\.13/).first()).toBeVisible();
  await dialog.getByRole('button',{name:/3 Raten-Aufgaben erstellen|Create 3 installment tasks/i}).click();
  await expect(dialog).toBeHidden();

  expect(taskRequests).toHaveLength(3);
  expect(taskRequests.map(item=>item.assignee)).toEqual([2,2,2]);
  expect(taskRequests.map(item=>item.family)).toEqual(['family-1','family-1','family-1']);
  const scheduledTotal=taskRequests.reduce((sum,item)=>{
    const match=item.title.match(/(?:€|EUR\s*)?(\d+[.,]\d{2})/);return sum+(match?Number(match[1].replace(',','.')):0);
  },0);
  expect(Math.round(scheduledTotal*100)).toBe(1240);
  expect(settlementPosts).toBe(0);
});
