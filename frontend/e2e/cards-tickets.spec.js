import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

const catalog={pass_types:[{value:'loyalty_card',label:'Loyalty card'},{value:'voucher',label:'Voucher'},{value:'coupon',label:'Coupon'},{value:'ticket',label:'Ticket'},{value:'boarding_pass',label:'Boarding pass'}],icons:[{key:'card',group:'general',label_de:'Karte',label_en:'Card',glyph:'▣',accent:'#6750A4'},{key:'gift',group:'general',label_de:'Geschenk',label_en:'Gift',glyph:'🎁',accent:'#A43D73'},{key:'ticket',group:'events',label_de:'Ticket',label_en:'Ticket',glyph:'🎟',accent:'#6750A4'}],color_modes:['custom','auto'],undo_window:{default_minutes:10,min_minutes:1,max_minutes:1440}};

async function installPassApi(page){
 let cards=[];
 await page.route('**/api/loyalty-cards/**',async route=>{
  const request=route.request();const method=request.method();const path=new URL(request.url()).pathname;let body={};try{body=request.postDataJSON()||{}}catch{}
  const json=(value,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(value)});
  if(path.endsWith('/catalog/')&&method==='GET')return json(catalog);
  if(path.endsWith('/sync/')&&method==='GET')return json(cards.filter(card=>!card.archived));
  if(path.endsWith('/loyalty-cards/')&&method==='POST'){
   const icon=catalog.icons.find(row=>row.key===body.icon_key);
   const card={id:`pass-${cards.length+1}`,created_by:1,created_by_name:'alex',shared_with:[],can_edit:true,archived:false,lifecycle_status:'active',can_restore:false,resolved_color:body.color_mode==='auto'?(icon?.accent||body.color):body.color,holder_display:body.holder_name||'',created_at:new Date().toISOString(),updated_at:new Date().toISOString(),...body};cards=[card,...cards];return json(card,201);
  }
  const redeem=path.match(/\/loyalty-cards\/([^/]+)\/redeem\/$/);if(redeem&&method==='POST'){
   const index=cards.findIndex(card=>card.id===redeem[1]);cards[index]={...cards[index],archived:true,lifecycle_status:'used',can_restore:true,archive_reason:'used',used_at:new Date().toISOString(),restore_until:new Date(Date.now()+600000).toISOString()};return json(cards[index]);
  }
  const restore=path.match(/\/loyalty-cards\/([^/]+)\/restore\/$/);if(restore&&method==='POST'){
   const index=cards.findIndex(card=>card.id===restore[1]);cards[index]={...cards[index],archived:false,lifecycle_status:'active',can_restore:false,archive_reason:'',used_at:null,restore_until:null};return json(cards[index]);
  }
  return json([]);
 });
}

test('voucher shows generic type branding and redeem can be undone',async({page})=>{
 await installApiMocks(page,{language:'de'});await installPassApi(page);
 await page.goto('/?page=more');await page.waitForLoadState('networkidle');
 await page.getByRole('button',{name:'Karten & Tickets',exact:true}).click();
 await page.getByRole('button',{name:'Karte / Ticket hinzufügen'}).click();
 const editor=page.getByRole('dialog');
 await editor.getByLabel('Name').fill('10 € Gutschein');
 await editor.locator('select').first().selectOption('voucher');
 await editor.locator('select').nth(1).selectOption('gift');
 await editor.getByLabel('Barcode-/Passwert').fill('VOUCHER-123');
 await editor.getByRole('button',{name:'Pass speichern'}).click();

 const passButton=page.getByRole('button',{name:/10 € Gutschein/});
 await expect(passButton).toBeVisible();
 await expect(passButton).toContainText('Gutschein');
 await passButton.click();
 await expect(page.getByRole('dialog').locator('.pass-type-badge')).toHaveText('Gutschein');
 await page.getByRole('dialog').getByRole('button',{name:'Einlösen / verwenden'}).click();
 const confirm=page.getByRole('alertdialog');
 await expect(confirm.getByRole('heading',{name:'Pass verwenden?'})).toBeVisible();
 await confirm.getByRole('button',{name:'Einlösen / verwenden'}).click();
 await expect(page.getByText('Verwendet',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Verwendung rückgängig'})).toBeVisible();
 await page.getByRole('button',{name:'Verwendung rückgängig'}).click();
 await expect(page.getByText('Pass wiederhergestellt.')).toBeVisible();
 await expect(page.getByRole('button',{name:'Einlösen / verwenden'})).toBeVisible();
});

test('cards and tickets layout keeps type affordances inside mobile viewport',async({page})=>{
 await installApiMocks(page,{language:'de'});await installPassApi(page);
 await page.setViewportSize({width:390,height:844});
 await page.goto('/?page=more');await page.getByRole('button',{name:'Karten & Tickets',exact:true}).click();
 await page.getByRole('button',{name:'Karte / Ticket hinzufügen'}).click();
 const editor=page.getByRole('dialog');await editor.getByLabel('Name').fill('Konzertticket');await editor.locator('select').first().selectOption('ticket');await editor.locator('select').nth(1).selectOption('ticket');await editor.getByLabel('Barcode-/Passwert').fill('TICKET-42');await editor.getByRole('button',{name:'Pass speichern'}).click();
 const card=page.locator('.wallet-card').filter({hasText:'Konzertticket'});await expect(card).toBeVisible();await expect(card.getByText('Ticket',{exact:true})).toBeVisible();
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);expect(overflow).toBeLessThanOrEqual(1);
});
