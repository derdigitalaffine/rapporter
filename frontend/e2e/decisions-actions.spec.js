import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

async function expectMinTarget(locator){
  const box=await locator.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);
}

test('decisions hub keeps canonical action hierarchy and explicit button semantics',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page);
  const decision={
    id:'decision-1',family:'family-1',question:'Urlaubsziel?',mode:'single',anonymous:false,is_open:true,
    can_vote:true,can_close:true,total_voters:1,my_option_ids:['option-1'],closes_at:null,context:null,
    options:[
      {id:'option-1',label:'Nordsee',votes:1,voters:[{name:'Alex'}]},
      {id:'option-2',label:'Berge',votes:0,voters:[]},
    ],
  };
  await page.route('**/api/decisions/**',async route=>{
    const request=route.request();
    const url=new URL(request.url());
    if(url.pathname==='/api/decisions/'&&request.method()==='GET')return json(route,[decision]);
    return json(route,decision);
  });

  await page.goto('/?page=decisions');
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading',{name:'Entscheidungen'})).toBeVisible();

  const back=page.getByRole('button',{name:'Zurück'});
  await expect(back).toHaveClass(/\bghost\b/);
  await expect(back).toHaveClass(/\bicon-button\b/);
  await expect(back).toHaveAttribute('type','button');
  await expectMinTarget(back);

  const newDecision=page.getByRole('button',{name:'Neue Entscheidung'});
  await expect(newDecision).toHaveClass(/\bprimary\b/);
  await expect(newDecision).toHaveAttribute('type','button');
  await newDecision.click();

  const form=page.locator('.decision-create');
  const closeForm=form.locator('.decision-form-head').getByRole('button',{name:'Abbrechen'});
  await expect(closeForm).toHaveClass(/\bghost\b/);
  await expect(closeForm).toHaveClass(/\bicon-button\b/);
  await expect(closeForm).toHaveAttribute('type','button');
  await expectMinTarget(closeForm);

  const addOption=form.getByRole('button',{name:'Option hinzufügen'});
  await expect(addOption).toHaveClass(/\bsecondary\b/);
  await expect(addOption).toHaveAttribute('type','button');
  await addOption.click();
  const removeOption=form.getByRole('button',{name:'Option entfernen 3'});
  await expect(removeOption).toHaveClass(/\bghost\b/);
  await expect(removeOption).toHaveClass(/\bicon-button\b/);
  await expect(removeOption).not.toHaveClass(/\bghost-danger\b/);
  await expect(removeOption).toHaveAttribute('type','button');
  await expectMinTarget(removeOption);

  const create=form.getByRole('button',{name:'Entscheidung erstellen'});
  await expect(create).toHaveClass(/\bprimary\b/);
  await expect(create).toHaveAttribute('type','submit');
  await closeForm.click();

  const saveVote=page.getByRole('button',{name:'Stimme speichern'});
  const retract=page.getByRole('button',{name:'Meine Stimme löschen'});
  const closeDecision=page.getByRole('button',{name:'Entscheidung schließen'});
  await expect(saveVote).toHaveClass(/\bprimary\b/);
  await expect(retract).toHaveClass(/\bsecondary\b/);
  await expect(closeDecision).toHaveClass(/\bghost\b/);
  await expect(closeDecision).toHaveClass(/\bghost-danger\b/);
  for(const action of [saveVote,retract,closeDecision])await expect(action).toHaveAttribute('type','button');
  await expectMinTarget(closeDecision);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  await page.setViewportSize({width:1440,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});
