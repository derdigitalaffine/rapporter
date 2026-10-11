const DAY=86400000;
const CONCRETE_PRECISIONS=new Set(['range','exact']);
const CONCRETE_STAGES=new Set(['scheduled','active']);
const WISH_STAGES=new Set(['idea','planning']);
const SEASON_MONTH={spring:3,summer:6,autumn:9,winter:12};

export function tripDateKey(value){
 if(!value)return null;
 const [y,m,d]=String(value).slice(0,10).split('-').map(Number);
 if(!Number.isInteger(y)||!Number.isInteger(m)||!Number.isInteger(d))return null;
 const key=Date.UTC(y,m-1,d);
 return Number.isFinite(key)?key:null;
}

export function tripTodayKey(now=new Date()){
 return Date.UTC(now.getFullYear(),now.getMonth(),now.getDate());
}

export function tripCountdown(row,words,now=new Date()){
 const today=tripTodayKey(now),start=tripDateKey(row?.starts_on),end=tripDateKey(row?.ends_on);
 if(start==null||end==null)return '';
 const until=Math.round((start-today)/DAY);
 if(until>1)return words.inDays.replace('{{count}}',until);
 if(until===1)return words.tomorrow;
 if(until===0)return words.today;
 if(today<=end){
  const day=Math.round((today-start)/DAY)+1;
  const total=Math.round((end-start)/DAY)+1;
  return words.tripDay.replace('{{day}}',day).replace('{{total}}',total);
 }
 return words.finished;
}

export function isTripWish(row){
 return WISH_STAGES.has(row?.stage);
}

function concreteCandidate(row,today){
 if(row?.archived)return false;
 if(row?.stage&& !CONCRETE_STAGES.has(row.stage))return false;
 if(row?.date_precision&&!CONCRETE_PRECISIONS.has(row.date_precision))return false;
 const start=tripDateKey(row?.starts_on),end=tripDateKey(row?.ends_on);
 return start!=null&&end!=null&&end>=today;
}

function wishDateKey(row){
 const concrete=tripDateKey(row?.starts_on);
 if(concrete!=null)return concrete;
 const year=Number(row?.date_year);
 if(!Number.isInteger(year)||year<1)return Number.MAX_SAFE_INTEGER;
 if(row?.date_precision==='month'&&Number.isInteger(Number(row?.date_month))){
  return Date.UTC(year,Number(row.date_month)-1,1);
 }
 if(row?.date_precision==='season'&&SEASON_MONTH[row?.date_season]){
  return Date.UTC(year,SEASON_MONTH[row.date_season]-1,1);
 }
 return Date.UTC(year,0,1);
}

function wishCandidate(row,today){
 if(row?.archived||!isTripWish(row))return false;
 const end=tripDateKey(row?.ends_on);
 return end==null||end>=today;
}

export function nextRelevantTrip(rows,now=new Date(),{includeWishes=false}={}){
 const today=tripTodayKey(now);
 const concrete=[...(rows||[])]
  .filter(row=>concreteCandidate(row,today))
  .sort((a,b)=>{
   const aStart=tripDateKey(a.starts_on),bStart=tripDateKey(b.starts_on);
   const aActive=aStart<=today?0:1,bActive=bStart<=today?0:1;
   return aActive-bActive||aStart-bStart||String(a.title||'').localeCompare(String(b.title||''));
  })[0]||null;
 if(concrete||!includeWishes)return concrete;
 return [...(rows||[])]
  .filter(row=>wishCandidate(row,today))
  .sort((a,b)=>wishDateKey(a)-wishDateKey(b)||Number(a.stage==='planning')-Number(b.stage==='planning')||String(a.title||'').localeCompare(String(b.title||'')))[0]||null;
}