import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

async function bootOrder(page){
  const state=await installApiMocks(page,{dismissOnboarding:true});
  state.shoppingLists[0].items=[
    {id:'item-milk',shopping_list:'shop-1',name:'Milch',quantity:'1 l',category:'Kühlung',aisle:'Kühlregal',note:'',favorite:true,checked:false,added_by_name:'Sam',position:1000},
    {id:'item-bread',shopping_list:'shop-1',name:'Brot',quantity:'1',category:'Backwaren',aisle:'',note:'',favorite:false,checked:false,added_by_name:'Alex',position:2000},
    {id:'item-eggs',shopping_list:'shop-1',name:'Eier',quantity:'10',category:'Kühlung',aisle:'',note:'',favorite:false,checked:false,added_by_name:'Alex',position:3000},
  ];
  const writes=[];
  await page.route('**/api/smart/shopping-lists/*/reorder/',async route=>{
    const body=route.request().postDataJSON()||{};
    writes.push(body.item_ids||[]);
    (body.item_ids||[]).forEach((id,index)=>{
      const item=state.shoppingLists[0].items.find(row=>String(row.id)===String(id));
      if(item)item.position=(index+1)*1000;
    });
    return route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true})});
  });
  await page.goto('/?page=shopping');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('.shopping-order-row')).toHaveCount(3);
  return {state,writes};
}

async function names(page){return page.locator('.shopping-order-row .smart-title strong').allTextContents()}

test('planning reorder stays visible, touch-safe and reload-persistent while row chrome stays quiet',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const {writes}=await bootOrder(page);
  const moveDown=page.getByRole('button',{name:'Milch nach unten'});
  const dragHandle=page.getByRole('button',{name:'Milch verschieben'});
  const moveBox=await moveDown.boundingBox();const dragBox=await dragHandle.boundingBox();
  expect(moveBox?.width).toBeGreaterThanOrEqual(44);expect(moveBox?.height).toBeGreaterThanOrEqual(44);
  expect(dragBox?.width).toBeGreaterThanOrEqual(44);expect(dragBox?.height).toBeGreaterThanOrEqual(44);
  await expect(page.locator('.shopping-order-row .favorite-badge')).toHaveCount(0);
  await expect(page.locator('.shopping-order-row > .row-action')).toHaveCount(0);
  await expect(page.locator('.shopping-progress-line')).toHaveCount(0);
  await expect(page.locator('.shopping-progress-track')).toHaveCount(0);
  await moveDown.focus();await page.keyboard.press('Enter');
  await expect.poll(()=>writes.length).toBe(1);
  expect(writes[0]).toEqual(['item-bread','item-milk','item-eggs']);
  await expect.poll(()=>names(page)).toEqual(['Brot','Milch','Eier']);
  await expect(page.getByText(/Milch verschoben: Position 2 von 3/)).toBeAttached();
  await page.reload();await page.waitForLoadState('networkidle');
  await expect.poll(()=>names(page)).toEqual(['Brot','Milch','Eier']);
});

test('planning pointer drag uses the handle and persists the same canonical order',async({page})=>{
  const {writes}=await bootOrder(page);
  const orderList=page.locator('.shopping-order-list');
  await orderList.evaluate(element=>element.scrollIntoView({block:'start'}));
  const source=page.getByRole('button',{name:'Milch verschieben'});const target=page.getByRole('button',{name:'Eier verschieben'});
  await expect(source).toBeVisible();await expect(target).toBeVisible();
  const sourceBox=await source.boundingBox();const targetBox=await target.boundingBox();
  expect(sourceBox).not.toBeNull();expect(targetBox).not.toBeNull();
  const viewport=page.viewportSize();
  expect(sourceBox.y+sourceBox.height).toBeLessThanOrEqual(viewport.height);
  expect(targetBox.y+targetBox.height).toBeLessThanOrEqual(viewport.height);
  await page.mouse.move(sourceBox.x+sourceBox.width/2,sourceBox.y+sourceBox.height/2);
  await page.mouse.down();
  await page.mouse.move(targetBox.x+targetBox.width/2,targetBox.y+targetBox.height/2,{steps:8});
  await page.mouse.up();
  await expect.poll(()=>writes.length).toBe(1);
  expect(writes[0]).toEqual(['item-bread','item-eggs','item-milk']);
  await expect.poll(()=>names(page)).toEqual(['Brot','Eier','Milch']);
});
