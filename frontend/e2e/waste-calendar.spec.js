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

test('Today shows exactly the next two waste collections with detected colors',async({page})=>{
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
  await expect(section.locator('.today-event-icon.waste-rest')).toHaveCount(1);
  await expect(section.locator('.today-event-icon.waste-yellow')).toHaveCount(1);
});

test('Calendar maps rest, yellow, bio and paper collections to their semantic icon colors',async({page})=>{
  const state=await installApiMocks(page,{authenticated:true,language:'de',dismissOnboarding:true});
  state.events.push(
    wasteEvent('waste-rest','Restmüll',24),
    wasteEvent('waste-yellow','Gelbe Tonne',48),
    wasteEvent('waste-bio','Biomüll',72),
    wasteEvent('waste-paper','Papiertonne',96),
  );

  await page.goto('/?page=calendar');
  await page.waitForLoadState('networkidle');

  const expected={
    'Restmüll':['waste-rest','rgb(236, 239, 241)'],
    'Gelbe Tonne':['waste-yellow','rgb(255, 242, 168)'],
    'Biomüll':['waste-bio','rgb(234, 215, 197)'],
    'Papiertonne':['waste-paper','rgb(220, 236, 255)'],
  };
  for(const [title,[className,color]] of Object.entries(expected)){
    const row=page.getByRole('button',{name:new RegExp(title)});
    await expect(row).toBeVisible();
    const icon=row.locator(`.agenda-source-icon.${className}`);
    await expect(icon).toHaveCount(1);
    await expect(icon).toHaveCSS('background-color',color);
  }
});
