const DAY=86400000;

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

export function nextRelevantTrip(rows,now=new Date()){
 const today=tripTodayKey(now);
 return [...(rows||[])]
  .filter(row=>{
   const start=tripDateKey(row?.starts_on),end=tripDateKey(row?.ends_on);
   return !row?.archived&&start!=null&&end!=null&&end>=today;
  })
  .sort((a,b)=>{
   const aStart=tripDateKey(a.starts_on),bStart=tripDateKey(b.starts_on);
   const aActive=aStart<=today?0:1,bActive=bStart<=today?0:1;
   return aActive-bActive||aStart-bStart||String(a.title||'').localeCompare(String(b.title||''));
  })[0]||null;
}
