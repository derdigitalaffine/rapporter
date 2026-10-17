export const SHOPPING_ITEM_SUGGESTION_VERSION=1;

const UNIT_PATTERN='kg|g|ml|l|stück|stueck|stk|st|paket|packung|pkg';
const UNIT_RE=new RegExp(`^(${UNIT_PATTERN})$`,'i');

function normalizeText(value){
  return String(value??'').normalize('NFKC').replace(/\s+/g,' ').trim();
}

function normalizeUnit(value){
  const raw=normalizeText(value).toLocaleLowerCase('de-DE');
  if(!UNIT_RE.test(raw))return '';
  if(['stück','stueck','stk','st'].includes(raw))return 'Stück';
  if(['paket','packung','pkg'].includes(raw))return 'Paket';
  return raw;
}

function suggestion(field,value,reason,confidence=1){
  return {field,value,confidence,source:'local-parser',reason};
}

export function parseShoppingItemInput(raw){
  const normalizedInput=normalizeText(raw);
  const result={
    version:SHOPPING_ITEM_SUGGESTION_VERSION,
    normalizedInput,
    values:{name:normalizedInput,quantity:'',category:''},
    suggestions:[],
  };
  if(!normalizedInput)return result;

  // A count marker is only interpreted when the user explicitly writes x/×.
  // This deliberately leaves product names such as "6er Eier" untouched.
  const counted=normalizedInput.match(/^(\d+(?:[.,]\d+)?)\s*[x×]\s+(.+)$/i);
  if(counted){
    const count=normalizeText(counted[1]);
    const remainder=normalizeText(counted[2]);
    const packed=remainder.match(new RegExp(`^(.+?)\\s+(\\d+(?:[.,]\\d+)?)\\s*(${UNIT_PATTERN})$`,'i'));
    const name=normalizeText(packed?packed[1]:remainder);
    if(name){
      const quantity=packed
        ?`${count} × ${normalizeText(packed[2])} ${normalizeUnit(packed[3])}`
        :`${count} ×`;
      result.values={...result.values,name,quantity};
      if(name!==normalizedInput)result.suggestions.push(suggestion('name',name,'explicit-count-marker'));
      result.suggestions.push(suggestion('quantity',quantity,packed?'explicit-count-and-package':'explicit-count-marker'));
      return result;
    }
  }

  // Quantity/unit prefixes require both an explicit number and a known unit.
  // Bare leading numbers stay part of the name because they can be brands/models.
  const prefixed=normalizedInput.match(new RegExp(`^(\\d+(?:[.,]\\d+)?)\\s*(${UNIT_PATTERN})\\s+(.+)$`,'i'));
  if(prefixed){
    const name=normalizeText(prefixed[3]);
    const unit=normalizeUnit(prefixed[2]);
    if(name&&unit){
      const quantity=`${normalizeText(prefixed[1])} ${unit}`;
      result.values={...result.values,name,quantity};
      result.suggestions.push(suggestion('name',name,'leading-quantity-unit'));
      result.suggestions.push(suggestion('quantity',quantity,'leading-quantity-unit'));
    }
  }
  return result;
}

export function applyShoppingItemAutoguess(payload={}){
  const parsed=parseShoppingItemInput(payload.name);
  const next={...payload};
  if(parsed.values.name)next.name=parsed.values.name;
  if(!normalizeText(payload.quantity)&&parsed.values.quantity)next.quantity=parsed.values.quantity;
  // Category intentionally abstains in the network-free core. Later authorised
  // data packages can add a higher-priority suggestion without changing this contract.
  return {payload:next,suggestion:parsed};
}
