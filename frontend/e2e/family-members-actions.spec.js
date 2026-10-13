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

test('family members supports managed children and preserves invite actions on mobile',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page);

  const memberships=[
    {id:'member-1',family:'family-1',user:1,username:'alex',role:'owner',display_name:'Alex',avatar:''},
    {id:'member-2',family:'family-1',user:2,username:'sam',role:'adult',display_name:'Sam',avatar:''},
  ];
  const invitations=[{
    id:'invite-contract-1',family:'family-1',role:'adult',email:'invite@example.test',display_name:'Einladung Test',
    expires_at:'2099-01-01T12:00:00.000Z',accepted_at:null,revoked_at:null,active:true,
    delivery_status:'sent',last_sent_at:'2026-10-11T12:00:00.000Z',
  }];
  const childIdentity={baby:'baby-1',membership:'member-child-1',access_state:'managed',email_hint:''};
  const childProfile={id:'baby-1',membership:'member-child-1',display_name:'Mia',birth_date:'2021-05-06'};

  await page.route('**/api/memberships/',route=>json(route,memberships));
  await page.route('**/api/invitations/',route=>{
    if(route.request().method()==='POST'){
      const body=route.request().postDataJSON();
      const invite={id:`invite-${invitations.length+1}`,family:'family-1',family_name:'Musterfamilie',token:'token-new',...body,accepted_at:null,revoked_at:null,active:true,delivery_status:'sent',last_sent_at:new Date().toISOString()};
      invitations.unshift(invite);
      return json(route,invite,201);
    }
    return json(route,invitations);
  });
  await page.route('**/api/baby/managed-children/',route=>{
    const body=route.request().postDataJSON();
    expect(body.family).toBe('family-1');
    expect(body.display_name).toBe('Mia');
    expect(body.birth_date).toBe('2021-05-06');
    expect(body.client_identity_key).toBeTruthy();
    expect(body.email).toBeUndefined();
    expect(body.password).toBeUndefined();
    if(!memberships.some(member=>member.id==='member-child-1'))memberships.push({id:'member-child-1',family:'family-1',user:3,username:'child-managed',role:'child',display_name:'Mia',avatar:''});
    return json(route,childIdentity,201);
  });
  await page.route('**/api/baby/memberships/member-child-1/identity/',route=>json(route,childIdentity));
  await page.route('**/api/baby/profiles/baby-1/',route=>{
    if(route.request().method()==='PATCH'){
      const body=route.request().postDataJSON();
      childProfile.display_name=body.display_name;
      childProfile.birth_date=body.birth_date;
      const child=memberships.find(member=>member.id==='member-child-1');
      if(child)child.display_name=body.display_name;
    }
    return json(route,childProfile);
  });

  await page.goto('/?page=members');
  await page.waitForLoadState('networkidle');

  const back=page.locator('.page-head .back-button');
  await expect(back).toHaveAttribute('type','button');
  await expectClasses(back,'ghost','icon-button','back-button');
  await expectMinTarget(back);

  const addButton=page.locator('.page-head .fab-inline');
  await expect(addButton).toHaveAttribute('type','button');
  await expectMinTarget(addButton);

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

  await addButton.click();
  const addSheet=page.locator('.invite-sheet');
  const childChoice=addSheet.getByRole('button',{name:/Kind ohne eigenen Zugang/});
  const inviteChoice=addSheet.getByRole('button',{name:/Person einladen/});
  await expect(childChoice).toBeVisible();
  await expect(inviteChoice).toBeVisible();
  await expectMinTarget(childChoice);
  await expectMinTarget(inviteChoice);

  await childChoice.click();
  await page.getByLabel('Name',{exact:true}).fill('Mia');
  await page.getByLabel('Geburtsdatum').fill('2021-05-06');
  await page.getByRole('button',{name:'Kinderprofil anlegen'}).click();
  await expect(page.getByRole('button',{name:/Mia.*Kind/})).toBeVisible();

  await page.getByRole('button',{name:/Mia.*Kind/}).click();
  await expect(page.getByLabel('Geburtsdatum')).toHaveValue('2021-05-06');
  await page.getByLabel('Anzeigename').fill('Mia Marie');
  await page.getByLabel('Geburtsdatum').fill('2021-05-07');
  await page.locator('.member-sheet form > .primary').click();
  await expect(page.getByRole('button',{name:/Mia Marie.*Kind/})).toBeVisible();
  expect(childProfile.birth_date).toBe('2021-05-07');

  await addButton.click();
  await page.getByRole('button',{name:/Person einladen/}).click();
  const inviteSheet=page.locator('.invite-sheet');
  const inviteClose=inviteSheet.locator('.sheet-close');
  await expect(inviteClose).toHaveAttribute('type','button');
  await expectClasses(inviteClose,'ghost','icon-button','sheet-close');
  await expectMinTarget(inviteClose);
  await inviteSheet.getByLabel('E-Mail').fill('new@example.test');
  await inviteSheet.getByRole('button',{name:/Weiter/}).click();
  await expect(inviteSheet.getByRole('button',{name:'Einladung senden'})).toHaveAttribute('type','submit');
  await inviteSheet.getByRole('button',{name:'Einladung senden'}).click();
  await expect(inviteSheet.getByText('new@example.test')).toBeVisible();

  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});
