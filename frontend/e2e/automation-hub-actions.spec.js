import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function openAutomationHub(page){
  const state=await installApiMocks(page);
  state.automationRules.push({
    id:'rule-1',
    family:'family-1',
    name:'Morgenroutine',
    trigger_type:'daily',
    trigger_config:{time:'08:00'},
    action_type:'task_create',
    action_config:{title:'Tasche packen'},
    enabled:true,
    executions:[],
  });
  await page.goto('/?page=automations');
  await expect(page.locator('.automation-stepper')).toBeVisible();
}

async function expectMinTarget(locator){
  const box=await locator.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);
}

test('automation hub uses canonical action semantics and accessible state',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await openAutomationHub(page);

  const pageBack=page.locator('.page-head .back-button');
  await expect(pageBack).toHaveClass(/\bghost\b/);
  await expect(pageBack).toHaveClass(/\bicon-button\b/);
  await expect(pageBack).toHaveAttribute('aria-label',/.+/);
  await expectMinTarget(pageBack);

  const steps=page.locator('.automation-stepper button');
  await expect(steps.first()).toHaveAttribute('aria-current','step');
  await expectMinTarget(steps.first());
  await expect(steps.nth(1)).toBeDisabled();

  const ruleActions=page.locator('.rule-row').first().locator('.rule-actions button');
  await expect(ruleActions).toHaveCount(3);

  const toggle=ruleActions.nth(0);
  await expect(toggle).toHaveClass(/\bghost\b/);
  await expect(toggle).toHaveClass(/\bicon-button\b/);
  await expect(toggle).toHaveClass(/\bactive\b/);
  await expect(toggle).toHaveAttribute('aria-pressed','true');
  await expect(toggle).toHaveAttribute('aria-label',/.+/);

  const run=ruleActions.nth(1);
  await expect(run).toHaveClass(/\bghost\b/);
  await expect(run).toHaveClass(/\bicon-button\b/);
  await expect(run).toHaveAttribute('aria-label',/.+/);

  const remove=ruleActions.nth(2);
  await expect(remove).toHaveClass(/\bghost\b/);
  await expect(remove).toHaveClass(/\bicon-button\b/);
  await expect(remove).toHaveClass(/\bghost-danger\b/);
  await expect(remove).toHaveAttribute('aria-label',/.+/);

  for(const action of [toggle,run,remove])await expectMinTarget(action);

  const mobileOverflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
  expect(mobileOverflow).toBeLessThanOrEqual(1);

  await page.setViewportSize({width:1440,height:900});
  const desktopOverflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
  expect(desktopOverflow).toBeLessThanOrEqual(1);
});

test('builder keeps one primary progression action and canonical back controls',async({page})=>{
  await openAutomationHub(page);

  await page.locator('.builder-choice').first().click();
  const nav=page.locator('.builder-nav');
  await expect(nav.locator('button').first()).toHaveClass(/\bsecondary\b/);
  await expect(nav.locator('button').last()).toHaveClass(/\bprimary\b/);

  await nav.locator('button').last().click();
  const builderBack=page.locator('.builder-choice-head .back-button');
  await expect(builderBack).toHaveClass(/\bghost\b/);
  await expect(builderBack).toHaveClass(/\bicon-button\b/);
  await expect(builderBack).toHaveAttribute('aria-label',/.+/);
  await expectMinTarget(builderBack);
});
