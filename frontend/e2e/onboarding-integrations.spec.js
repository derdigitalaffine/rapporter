import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const integrationStep=page=>page.getByRole('button',{name:/Aktiviere eine Integration oder füge eine Integration hinzu/});

test('onboarding shows open integration step and opens the existing hub',async({page})=>{
  const state=await installApiMocks(page,{dismissOnboarding:false});
  state.integrations.length=0;

  await page.goto('/');

  const step=integrationStep(page);
  await expect(step).toBeVisible();
  await expect(step).toContainText('Empfohlen');
  await step.click();
  await expect(page).toHaveURL(/page=integrations/);
  await expect(page.getByRole('heading',{name:'Integrationen',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Integration hinzufügen',exact:true})).toBeVisible();
});

test('enabled integration is completed while disabled-only state stays open',async({page})=>{
  const state=await installApiMocks(page,{dismissOnboarding:false});
  state.events.length=0;
  state.integrations[0].enabled=false;

  await page.goto('/');
  await expect(integrationStep(page)).not.toContainText('Erledigt');

  state.integrations[0].enabled=true;
  await page.reload();
  await expect(integrationStep(page)).toContainText('Erledigt');
});

test('returning from integration hub refreshes completion without manual reload',async({page})=>{
  const state=await installApiMocks(page,{dismissOnboarding:false});
  state.events.length=0;
  state.integrations.length=0;

  await page.goto('/');
  await integrationStep(page).click();
  await expect(page).toHaveURL(/page=integrations/);

  state.integrations.push({id:'integration-new',family:'family-1',name:'Open-Meteo',kind:'weather',enabled:true,endpoint:'',config:{adapter:'open_meteo'},last_sync_status:'success',last_sync_error:'',last_success_at:new Date().toISOString(),last_synced_at:new Date().toISOString(),next_sync_at:null});
  await page.goBack();

  await expect(page).toHaveURL(/\/$/);
  await expect(integrationStep(page)).toContainText('Erledigt');
  await expect(page.getByRole('button',{name:'Später weiter'})).toBeVisible();
});
