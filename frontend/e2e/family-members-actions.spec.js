import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const TARGET_EPSILON_PX=0.01;

function json(route,body,status=200){return route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)})}

async function expectMinTarget(locator){
  const box=await locator.boundingBox();
  expect((box?.width||0)+TARGET_EPSILON_PX).toBeGreaterThanOrEqual(44);
  expect((box?.height||0)+TARGET_EPSILON_PX).toBeGreaterThanOrEqual(44);
}

async function expectClasses(locator,...classes){
  const classList=await locator.evaluate(element=>[...element.classList]);
  expect(classList).toEqual(expect.arrayContaining(classes));
}

test('family members actions keep canonical variants and touch targets',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page);
  await page.route('**/api/invitations/',route=>json(route,[{
    id:'invite-contract-1',
    family:'family-1',
    role:'adult',
    email:'invite@example.test',
    display_name:'Einladung Test',
    expires_at:'2099-01-01T12:00:00.000Z',
    accepted_at:null,
    revoked_at:null,
    active:true,
    delivery_status:'sent',
    last_sent_at:'2026-10-11T12:00:00.000Z',
  }]));

  await page.goto('/?page=members');
  await page.waitForLoadState('networkidle');

  const back=page.locator('.page-head .back-button');
  await expect(back).toHaveAttribute('type','button');
  await expectClasses(back,'ghost','icon-button','back-button');
  await expectMinTarget(back);

  const inviteButton=page.locator('.page-head .fab-inline');
  await expect(inviteButton).toHaveAttribute('type','button');
  await expectMinTarget(inviteButton);

  const memberRow=page.locator('.member-profile-row').first();
  await expect(memberRow).toHaveAttribute('type','button');
  await expectMinTarget(memberRow);

  const renew=page.getByRole('button',{name:'Erneut senden'});
  await expect(renew).toHaveAttribute('type','button');
  await expectClasses(renew,'secondary');
  await expectMinTarget(renew);

  const revoke=page.locator('.invite-actions .ghost-danger');
  await expect(revoke).toHaveAttribute('type','button');
  await expectClasses(revoke,'ghost','ghost-danger','secondary-danger');
  await expectMinTarget(revoke);

  await memberRow.click();
  const memberSheet=page.locator('.member-sheet');
  const memberClose=memberSheet.locator('.sheet-close');
  await expect(memberClose).toHaveAttribute('type','button');
  await expectClasses(memberClose,'ghost','icon-button','sheet-close');
  await expectMinTarget(memberClose);
  await expect(memberSheet.locator('form > .primary')).toHaveAttribute('type','submit');

  const remove=memberSheet.locator('.member-danger-zone .ghost-danger');
  await expect(remove).toHaveAttribute('type','button');
  await expectClasses(remove,'ghost','ghost-danger','destructive-wide');
  await expectMinTarget(remove);
  await memberClose.click();

  await inviteButton.click();
  const inviteSheet=page.locator('.invite-sheet');
  const inviteClose=inviteSheet.locator('.sheet-close');
  await expect(inviteClose).toHaveAttribute('type','button');
  await expectClasses(inviteClose,'ghost','icon-button','sheet-close');
  await expectMinTarget(inviteClose);

  await inviteSheet.getByLabel('E-Mail').fill('new@example.test');
  await inviteSheet.getByRole('button',{name:/Weiter zu Rolle/}).click();
  await expect(inviteSheet.getByRole('button',{name:'Einladung senden'})).toHaveAttribute('type','submit');

  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});
