import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function openIntegrationHub(page,query=''){
  await installApiMocks(page);
  await page.goto(`/?page=integrations${query}`);
  await expect(page.getByRole('heading',{name:'Integrationen',exact:true})).toBeVisible();
}

test('integration hub uses canonical action hierarchy',async({page})=>{
  await openIntegrationHub(page);

  const back=page.locator('.page-head .back-button');
  await expect(back).toHaveClass(/\bghost\b/);
  await expect(back).toHaveClass(/\bicon-button\b/);
  await expect(back).toHaveAttribute('aria-label',/.+/);

  const syncAll=page.locator('.sync-all-secondary');
  await expect(syncAll).toHaveClass(/\bsecondary\b/);
  await expect(syncAll).toHaveAttribute('aria-label',/.+/);

  const connectedCard=page.locator('.catalog-card',{hasText:'Open-Meteo'});
  await expect(connectedCard.getByRole('button',{name:'Weitere Verbindung'})).toHaveClass(/\bsecondary\b/);

  const availableCard=page.locator('.catalog-card',{hasText:'Abfallkalender'});
  await expect(availableCard.getByRole('button',{name:'Einrichten'})).toHaveClass(/\bprimary\b/);

  await page.locator('.integration-details summary').click();
  const disconnect=page.getByRole('button',{name:'Trennen'});
  await expect(disconnect).toHaveClass(/\btext-button\b/);
  await expect(disconnect).toHaveClass(/\bghost-danger\b/);
});

test('success actions expose one primary continuation and responsive icon actions stay usable',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await openIntegrationHub(page,'&integration_connected=Open-Meteo');

  const success=page.locator('.connection-success');
  await expect(success).toBeVisible();
  await expect(success.getByRole('link',{name:'Kalender ansehen'})).toHaveClass(/\bsecondary\b/);
  await expect(success.getByRole('link',{name:'Regel erstellen'})).toHaveClass(/\bprimary\b/);

  const close=success.getByRole('button',{name:'Hinweis schließen'});
  await expect(close).toHaveClass(/\bghost\b/);
  await expect(close).toHaveClass(/\bicon-button\b/);
  await expect(close).toHaveAttribute('title','Hinweis schließen');

  const syncAll=page.locator('.sync-all-secondary');
  const box=await syncAll.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);

  const mobileOverflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);

  await page.setViewportSize({width:1440,height:900});
  const desktopOverflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
  await expect(page.locator('.catalog-actions').first()).toHaveCSS('flex-wrap','wrap');
});
