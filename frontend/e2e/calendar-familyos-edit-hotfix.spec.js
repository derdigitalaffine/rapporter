import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function openCalendarEvent(page,title){
  await page.goto('/?page=calendar');
  await page.waitForLoadState('networkidle');
  await page.locator('.calendar-mobile-daystrip').getByRole('button',{name:new RegExp(title)}).click();
  await page.locator('.calendar-event-chip:visible').filter({hasText:title}).first().click();
  const detail=page.getByRole('dialog').filter({hasText:title});
  await expect(detail).toBeVisible();
  return detail;
}

test('legacy source-less FamilyOS calendar events keep the edit button',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const state=await installApiMocks(page,{dismissOnboarding:true});
  state.events[1]={
    ...state.events[1],
    type:'calendar.legacy',
    source:null,
    payload:{...state.events[1].payload,provider:'FamilyOS'},
  };

  const detail=await openCalendarEvent(page,'Kinderarzt');
  const editButton=detail.getByRole('button',{name:'Termin bearbeiten',exact:true});
  await expect(editButton).toBeVisible();
  await editButton.click();
  await expect(page.getByRole('dialog',{name:'Termin bearbeiten'})).toBeVisible();
});

test('source-backed calendar events stay read-only even with a FamilyOS-looking provider',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const state=await installApiMocks(page,{dismissOnboarding:true});
  state.events[1]={
    ...state.events[1],
    source:'integration-1',
    source_meta:{id:'integration-1',name:'Importierter Kalender',kind:'ics'},
    payload:{...state.events[1].payload,provider:'FamilyOS'},
  };

  const detail=await openCalendarEvent(page,'Kinderarzt');
  await expect(detail.getByRole('button',{name:'Termin bearbeiten',exact:true})).toHaveCount(0);
});
