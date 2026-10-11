import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const json=(route,body,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(body)});

async function expectMinTarget(locator){
  const box=await locator.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);
}

test('notification inbox keeps explicit button semantics across read and pagination actions',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await installApiMocks(page);
  let rows=[
    {id:'notification-1',family:'family-1',title:'Aufgabe fällig',body:'Wäsche aufhängen',read:false,read_at:null,resource_url:null,created_at:'2026-10-11T09:00:00Z'},
    {id:'notification-2',family:'family-1',title:'Einkauf aktualisiert',body:'Milch wurde ergänzt',read:false,read_at:null,resource_url:null,created_at:'2026-10-11T08:00:00Z'},
  ];
  const later={id:'notification-3',family:'family-1',title:'Frühere Mitteilung',body:'Archivierter Hinweis',read:true,read_at:'2026-10-10T08:00:00Z',resource_url:null,created_at:'2026-10-10T08:00:00Z'};

  await page.route('**/api/notifications/**',async route=>{
    const request=route.request();
    const url=new URL(request.url());
    const path=url.pathname;
    const method=request.method();
    if(path==='/api/notifications/'&&method==='GET'){
      if(url.searchParams.get('cursor'))return json(route,{results:[later],unread_count:0,next_cursor:null});
      return json(route,{results:rows,unread_count:rows.filter(row=>!row.read).length,next_cursor:'next-page'});
    }
    if(path==='/api/notifications/read-all/'&&method==='POST'){
      rows=rows.map(row=>({...row,read:true,read_at:row.read_at||'2026-10-11T10:00:00Z'}));
      return json(route,{updated:rows.length});
    }
    const match=path.match(/^\/api\/notifications\/([^/]+)\/$/);
    if(match&&method==='PATCH'){
      const id=match[1];
      rows=rows.map(row=>row.id===id?{...row,read:true,read_at:'2026-10-11T10:00:00Z'}:row);
      return json(route,rows.find(row=>row.id===id));
    }
    return json(route,{});
  });

  await page.goto('/?page=notifications');
  await page.waitForLoadState('networkidle');
  const inbox=page.locator('.notification-inbox');
  await expect(inbox.getByRole('heading',{name:'Mitteilungen'})).toBeVisible();

  const markAll=inbox.getByRole('button',{name:'Alle als gelesen markieren'});
  await expect(markAll).toHaveClass(/\bsecondary\b/);
  await expect(markAll).toHaveClass(/\bcompact\b/);
  await expect(markAll).toHaveAttribute('type','button');
  await expectMinTarget(markAll);

  const rowButtons=inbox.locator('.notification-inbox-row > button');
  await expect(rowButtons).toHaveCount(2);
  for(let index=0;index<2;index++)await expect(rowButtons.nth(index)).toHaveAttribute('type','button');
  await expectMinTarget(rowButtons.first());

  const loadMore=inbox.getByRole('button',{name:'Mehr laden'});
  await expect(loadMore).toHaveClass(/\bsecondary\b/);
  await expect(loadMore).toHaveAttribute('type','button');
  await expectMinTarget(loadMore);

  await rowButtons.first().click();
  await expect(inbox.locator('.notification-inbox-row').first()).toHaveClass(/\bread\b/);
  await expect(inbox.getByText('1 ungelesen')).toBeVisible();

  await markAll.click();
  await expect(inbox.getByText(/ungelesen/)).toHaveCount(0);
  await expect(inbox.locator('.notification-inbox-row.unread')).toHaveCount(0);

  await loadMore.click();
  await expect(inbox.getByText('Frühere Mitteilung')).toBeVisible();
  await expect(inbox.getByRole('button',{name:'Mehr laden'})).toHaveCount(0);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

  await page.setViewportSize({width:1440,height:900});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
});
