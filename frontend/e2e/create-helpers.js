function escapeRegExp(value){return String(value).replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}

export async function openCreateAction(page,label){
 const fab=page.locator('.global-create-fab');
 await fab.waitFor({state:'visible'});
 await fab.click();
 const palette=page.locator('.create-palette-sheet');
 await palette.waitFor({state:'visible'});
 const allToggle=palette.locator('.create-all-toggle');
 if(await allToggle.getAttribute('aria-expanded')!=='true')await allToggle.click();
 await palette.locator('.create-all-actions').waitFor({state:'visible'});
 const action=palette.locator('.create-action-list button').filter({hasText:new RegExp(`^\\s*${escapeRegExp(label)}\\s*$`)}).first();
 await action.waitFor({state:'visible'});
 await action.click();
}
