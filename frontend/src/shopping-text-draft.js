import {parseShoppingItemInput} from './shopping-item-autoguess.js';

export const SHOPPING_TEXT_MAX_LINES=80;

export function cleanShoppingTextLine(value){
  return String(value??'')
    .replace(/^\s*(?:(?:[-*•])\s+|\d+[.)]\s+|\[[ xX]\]\s+)/,'')
    .trim();
}

export function parseShoppingTextDraft(value){
  const rawLines=String(value??'')
    .split(/\r?\n/)
    .map(line=>line.trim())
    .filter(Boolean);
  const occurrences=new Map();
  const rows=rawLines.slice(0,SHOPPING_TEXT_MAX_LINES).map((raw,index)=>{
    const cleaned=cleanShoppingTextLine(raw);
    const count=(occurrences.get(raw)||0)+1;occurrences.set(raw,count);
    return {
      id:`draft-${index}`,
      signature:`${raw}\u0000${count}`,
      raw,
      cleaned,
      parsed:parseShoppingItemInput(cleaned),
    };
  });
  return {rows,overLimit:rawLines.length>SHOPPING_TEXT_MAX_LINES,total:rawLines.length};
}

export function reconcileShoppingTextLineIds(previousRows,nextRows,currentIds,idFactory){
  const next=new Map();
  const used=new Set();
  for(const row of nextRows){
    const existing=currentIds.get(row.signature);
    if(existing&&!used.has(existing)){next.set(row.signature,existing);used.add(existing)}
  }
  for(let index=0;index<nextRows.length;index++){
    const row=nextRows[index];if(next.has(row.signature))continue;
    const previous=previousRows[index];const inherited=previous&&currentIds.get(previous.signature);
    if(inherited&&!used.has(inherited)){next.set(row.signature,inherited);used.add(inherited);continue}
    const created=idFactory();next.set(row.signature,created);used.add(created);
  }
  return next;
}
