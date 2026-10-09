const code=Number;

export function weatherCondition(value){
  const c=code(value);
  if(c===0)return {key:'clear',icon:'weather'};
  if(c===1)return {key:'mainlyClear',icon:'weather'};
  if(c===2)return {key:'partlyCloudy',icon:'weather'};
  if(c===3)return {key:'cloudy',icon:'weather'};
  if([45,48].includes(c))return {key:'fog',icon:'weather'};
  if([51,53,55,56,57].includes(c))return {key:'drizzle',icon:'rain'};
  if([61,63,65,66,67].includes(c))return {key:'rain',icon:'rain'};
  if([71,73,75,77].includes(c))return {key:'snow',icon:'frost'};
  if([80,81,82,85,86].includes(c))return {key:'showers',icon:'rain'};
  if([95,96,99].includes(c))return {key:'thunderstorm',icon:'warning'};
  return {key:'unknown',icon:'weather'};
}

export function weatherDescription(value,t){return t(`weatherUi.condition.${weatherCondition(value).key}`)}
export function temperature(value){return value==null?'–':`${Number(value).toLocaleString(undefined,{maximumFractionDigits:1})} °C`}
export function speed(value){return value==null?'–':`${Number(value).toLocaleString(undefined,{maximumFractionDigits:1})} km/h`}
export function millimeters(value){return value==null?'–':`${Number(value).toLocaleString(undefined,{maximumFractionDigits:1})} mm`}
export function percent(value){return value==null?'–':`${Math.round(Number(value))} %`}
export function localTime(value,language='de'){
  if(!value)return '–';
  const date=new Date(value);
  if(Number.isNaN(date.getTime()))return String(value).slice(11,16)||String(value);
  return new Intl.DateTimeFormat(language==='en'?'en-GB':'de-DE',{hour:'2-digit',minute:'2-digit'}).format(date);
}
export function dayLabel(dateValue,language='de',todayLabel='Heute'){
  if(!dateValue)return '';
  const date=new Date(`${dateValue}T12:00:00`);
  const now=new Date();
  const same=date.getFullYear()===now.getFullYear()&&date.getMonth()===now.getMonth()&&date.getDate()===now.getDate();
  if(same)return todayLabel;
  return new Intl.DateTimeFormat(language==='en'?'en-GB':'de-DE',{weekday:'short',day:'2-digit',month:'2-digit'}).format(date);
}
