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
  await expect(page.getByRole('heading',{name:'Ausgaben',exact:true})).toBeVisible();
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

  const settle=page.getByRole('button',{name:/Als abgerechnet markieren|Mark as settled/i});
  await expect(settle).toHaveClass(/\bsecondary\b/);
  const undo=page.locator('.settlement-history').getByRole('button',{name:/Abrechnung stornieren|Void settlement/i});
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
