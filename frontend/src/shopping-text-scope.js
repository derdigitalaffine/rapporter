export function shoppingTextScopeKey(familyId,listId){
  if(!familyId||!listId)return '';
  return `${String(familyId)}:${String(listId)}`;
}

export function currentShoppingList(lists,familyId,activeId){
  if(!familyId)return null;
  const scoped=(lists||[]).filter(row=>String(row.family)===String(familyId));
  return scoped.find(row=>String(row.id)===String(activeId))||scoped[0]||null;
}
