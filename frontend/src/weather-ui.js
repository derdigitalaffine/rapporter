const WEATHER_LABELS={
 de:{clear:'Klar',partly:'Leicht bewölkt',cloudy:'Bewölkt',fog:'Nebel',drizzle:'Nieselregen',rain:'Regen',snow:'Schnee',rainShowers:'Regenschauer',snowShowers:'Schneeschauer',thunderstorm:'Gewitter',weather:'Wetter'},
 en:{clear:'Clear',partly:'Partly cloudy',cloudy:'Cloudy',fog:'Fog',drizzle:'Drizzle',rain:'Rain',snow:'Snow',rainShowers:'Rain showers',snowShowers:'Snow showers',thunderstorm:'Thunderstorm',weather:'Weather'},
 fr:{clear:'Dégagé',partly:'Partiellement nuageux',cloudy:'Nuageux',fog:'Brouillard',drizzle:'Bruine',rain:'Pluie',snow:'Neige',rainShowers:'Averses',snowShowers:'Averses de neige',thunderstorm:'Orage',weather:'Météo'},
 nl:{clear:'Helder',partly:'Halfbewolkt',cloudy:'Bewolkt',fog:'Mist',drizzle:'Motregen',rain:'Regen',snow:'Sneeuw',rainShowers:'Regenbuien',snowShowers:'Sneeuwbuien',thunderstorm:'Onweer',weather:'Weer'},
 th:{clear:'ท้องฟ้าแจ่มใส',partly:'มีเมฆบางส่วน',cloudy:'มีเมฆมาก',fog:'หมอก',drizzle:'ฝนปรอย',rain:'ฝน',snow:'หิมะ',rainShowers:'ฝนเป็นช่วง ๆ',snowShowers:'หิมะตกเป็นช่วง ๆ',thunderstorm:'พายุฝนฟ้าคะนอง',weather:'สภาพอากาศ'},
};

function labelsFor(language='de'){
 const code=String(language||'de').toLowerCase().split('-')[0];
 return WEATHER_LABELS[code]||WEATHER_LABELS.de;
}

export function weatherLabel(code,language='de'){
 const labels=labelsFor(language);const n=Number(code);
 if(n===0)return labels.clear;if([1,2].includes(n))return labels.partly;if(n===3)return labels.cloudy;if([45,48].includes(n))return labels.fog;if(n>=51&&n<=57)return labels.drizzle;if(n>=61&&n<=67)return labels.rain;if(n>=71&&n<=77)return labels.snow;if(n>=80&&n<=82)return labels.rainShowers;if([85,86].includes(n))return labels.snowShowers;if(n>=95)return labels.thunderstorm;return labels.weather;
}
export function weatherGlyph(code){const n=Number(code);if(n===0)return'☀️';if([1,2].includes(n))return'🌤️';if(n===3)return'☁️';if([45,48].includes(n))return'🌫️';if(n>=71&&n<=77||[85,86].includes(n))return'🌨️';if(n>=95)return'⛈️';if(n>=51&&n<=67||n>=80&&n<=82)return'🌧️';return'🌦️'}
export const value=(input,suffix='')=>input===null||input===undefined?'–':`${input}${suffix}`;
