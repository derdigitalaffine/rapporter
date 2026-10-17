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
  const rows=rawLines.slice(0,SHOPPING_TEXT_MAX_LINES).map((raw,index)=>{
    const cleaned=cleanShoppingTextLine(raw);
    return {
      id:`draft-${index}`,
      raw,
      cleaned,
      parsed:parseShoppingItemInput(cleaned),
    };
  });
  return {rows,overLimit:rawLines.length>SHOPPING_TEXT_MAX_LINES,total:rawLines.length};
}
