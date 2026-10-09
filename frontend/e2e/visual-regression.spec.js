import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const viewports={mobile:{width:390,height:844},tablet:{width:1024,height:768},desktop:{width:1440,height:900}};
const pages=[['today','home'],['tasks','tasks'],['shopping','shopping'],['calendar','calendar'],['members','members'],['integrations','integrations'],['automations','automations'],['more','more']];

async function boot(page,target,viewport){
  await page.setViewportSize(viewport);
  await page.addInitScript(()=>{
    const fixed=Date.parse('2026-10-09T10:00:00+02:00');
    const NativeDate=Date;
    class FixedDate extends NativeDate{constructor(...args){super(...(args.length?args:[fixed]))}static now(){return fixed}}
    FixedDate.parse=NativeDate.parse;FixedDate.UTC=NativeDate.UTC;window.Date=FixedDate;
  });
  await installApiMocks(page,{dismissOnboarding:true});
  await page.goto(target==='home'?'/' : `/?page=${target}`);
  await page.waitForLoadState('networkidle');
  await page.addStyleTag({content:'*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}'});
}

async function visual(page,name){
  await expect(page).toHaveScreenshot(`${name}.png`,{
    fullPage:true,
    animations:'disabled',
    caret:'hide',
    maxDiffPixelRatio:0.001,
    mask:[page.locator('.loading'),page.locator('.status-pill')],
  });
}

test.describe('visual regression gates',()=>{
  test.skip(({project})=>project.name!=='mobile-chromium','Generate one canonical Linux/Chromium baseline set.');
  for(const [viewportName,viewport] of Object.entries(viewports)){
    for(const [name,target] of pages){
      test(`${viewportName} ${name}`,async({page})=>{await boot(page,target,viewport);await visual(page,`${viewportName}-${name}`)});
    }
  }
  for(const [viewportName,viewport] of Object.entries({mobile:viewports.mobile,desktop:viewports.desktop})){
    test(`${viewportName} task editor`,async({page})=>{await boot(page,'tasks',viewport);await page.locator('.global-create-fab').click();await expect(page.getByRole('dialog').getByRole('heading',{name:'Aufgabe hinzufügen'})).toBeVisible();await visual(page,`${viewportName}-task-editor`)});
    test(`${viewportName} event editor`,async({page})=>{await boot(page,'calendar',viewport);await page.locator('.global-create-fab').click();await expect(page.getByRole('dialog').getByRole('heading',{name:'Termin hinzufügen'})).toBeVisible();await visual(page,`${viewportName}-event-editor`)});
  }
});
