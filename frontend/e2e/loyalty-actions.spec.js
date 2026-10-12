import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

async function expectMinTarget(locator){
  const box=await locator.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);
}

test('loyalty hub keeps canonical back, detail and destructive action semantics',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page);
  const cards=[{
    id:'card-1',family:'family-1',name:'Wochenkarte',pass_type:'ticket',barcode_value:'1234567890',barcode_format:'code128',
    holder_display:'Alex',holder_name:'Alex',customer_number:'WK-42',note:'',favorite:false,archived:false,lifecycle_status:'active',
    can_edit:true,can_restore:false,event_ends_at:null,resolved_color:'#6750A4',color:'#6750A4',icon_key:'ticket',logo:''
  }];
  await page.route('**/api/loyalty-cards/**',async route=>{
    const request=route.request();
    const url=new URL(request.url());
    if(url.pathname==='/api/loyalty-cards/sync/'&&request.method()==='GET')return json(route,cards);
    return json(route,{});
  });

  await page.goto('/?page=loyalty');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading',{name:'Karten & Tickets'})).toBeVisible();

  const back=page.getByRole('button',{name:'Zurück'});
  await expect(back).toHaveClass(/\bghost\b/);
  await expect(back).toHaveClass(/\bicon-button\b/);
  await expect(back).toHaveAttribute('type','button');
  await expectMinTarget(back);

  const sync=page.getByRole('button',{name:'Karten & Tickets synchronisieren'});
  await expect(sync).toHaveClass(/\bsecondary\b/);
  await expect(sync).toHaveAttribute('type','button');
  await expectMinTarget(sync);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  const pass=page.getByRole('button',{name:/Wochenkarte/});
  await expect(pass).toHaveAttribute('type','button');
  await pass.click();

  const detail=page.locator('.loyalty-detail');
  await expect(detail).toBeVisible();
  const close=detail.getByRole('button',{name:'Zurück'});
  await expect(close).toHaveClass(/\bghost\b/);
  await expect(close).toHaveClass(/\bicon-button\b/);
  await expect(close).toHaveClass(/\bsheet-close\b/);
  await expect(close).toHaveAttribute('type','button');
  await expectMinTarget(close);

  const fullscreen=detail.getByRole('button',{name:'Code groß anzeigen'});
  const redeem=detail.getByRole('button',{name:'Einlösen / verwenden'});
  const edit=detail.getByRole('button',{name:'Pass bearbeiten'});
  const archive=detail.getByRole('button',{name:'Archivieren'});
  await expect(fullscreen).toHaveClass(/\bprimary\b/);
  await expect(redeem).toHaveClass(/\bsecondary\b/);
  await expect(edit).toHaveClass(/\bsecondary\b/);
  await expect(archive).toHaveClass(/\bghost\b/);
  await expect(archive).toHaveClass(/\bghost-danger\b/);
  for(const action of [fullscreen,redeem,edit,archive])await expect(action).toHaveAttribute('type','button');
  await expectMinTarget(archive);

  await fullscreen.click();
  const cashier=detail.locator('.cashier-overlay');
  await expect(cashier).toBeVisible();
  const cashierClose=cashier.locator('.sheet-close');
  await expect(cashierClose).toHaveAccessibleName('Code-Ansicht schließen');
  await expect(cashierClose).toHaveClass(/\bghost\b/);
  await expect(cashierClose).toHaveClass(/\bicon-button\b/);
  await expect(cashierClose).toHaveAttribute('type','button');
  await expectMinTarget(cashierClose);
  await expect(cashier.getByRole('button',{name:'Code-Ansicht schließen'}).last()).toHaveClass(/\bprimary\b/);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  await page.setViewportSize({width:1440,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});
