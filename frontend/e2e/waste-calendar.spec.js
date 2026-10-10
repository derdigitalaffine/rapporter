import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

function wasteEvent(id,title,hours,payload={}){
  return {
    id,
    family:'family-1',
    source:'waste-source',
    type:'waste.collection',
    title,
    starts_at:new Date(Date.now()+hours*3600000).toISOString(),
    ends_at:null,
    actionable:true,
    payload:{provider:'Abfallkalender',...payload},
  };
}

test('Today shows exactly the next two waste collections with large semantic icons',async({page})=>{
  const state=await installApiMocks(page,{authenticated:true,language:'de',dismissOnboarding:true});
  state.events.push(
    wasteEvent('waste-rest','Restafall Bezirk 3',24),
    wasteEvent('waste-yellow','Abfuhr Verpackungen',48,{waste_kind:'yellow'}),
    wasteEvent('waste-paper','Altpapier',72),
  );

  await page.goto('/');
  await page.waitForLoadState('networkidle');

  const section=page.getByTestId('next-waste');
  await expect(section).toBeVisible();
  await expect(section.getByRole('heading',{name:'Nächste Müllabfuhr'})).toBeVisible();
  await expect(section).toContainText('Restafall Bezirk 3');
  await expect(section).toContainText('Abfuhr Verpackungen');
  await expect(section).not.toContainText('Altpapier');
  const rest=section.locator('.today-event-icon.waste-rest');
  const yellow=section.locator('.today-event-icon.waste-yellow');
  await expect(rest).toHaveCount(1);
  await expect(yellow).toHaveCount(1);
  await expect(rest).toHaveCSS('display','grid');
  await expect(rest).toHaveCSS('color','rgb(38, 50, 56)');
  await expect(yellow).toHaveCSS('color','rgb(111, 87, 0)');
  await expect(rest.locator('svg')).toHaveCSS('font-size','26px');
  await expect(yellow.locator('svg')).toHaveCSS('font-size','26px');
});

test('Calendar renders waste as compact typed special events instead of appointments',async({page})=>{
  const state=await installApiMocks(page,{authenticated:true,language:'de',dismissOnboarding:true});
  state.events.push(
    wasteEvent('waste-rest','Restmüll',24),
    wasteEvent('waste-yellow','Gelbe Tonne',48),
    wasteEvent('waste-bio','Biomüll',72),
    wasteEvent('waste-paper','Papiertonne',96),
  );

  await page.goto('/?page=calendar');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button',{name:'Liste',exact:true}).click();

  const expected={
    'Restmüll':['waste-rest','rgb(236, 239, 241)'],
    'Gelbe Tonne':['waste-yellow','rgb(255, 242, 168)'],
    'Biomüll':['waste-bio','rgb(234, 215, 197)'],
    'Papiertonne':['waste-paper','rgb(220, 236, 255)'],
  };
  for(const [title,[className,color]] of Object.entries(expected)){
    const row=page.locator('.agenda-waste').filter({hasText:title});
    await expect(row).toBeVisible();
    await expect(row).toContainText('MÜLLABFUHR');
    await expect(row.locator('.agenda-time')).toHaveCount(0);
    const marker=row.locator(`.waste-dot.${className}`);
    await expect(marker).toHaveCount(1);
    await expect(marker).toHaveCSS('background-color',color);
    await expect(marker.locator('svg')).toHaveCount(1);
  }
});
