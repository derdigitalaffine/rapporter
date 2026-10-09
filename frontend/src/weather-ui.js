export function weatherLabel(code,language='de'){
 const de=language.startsWith('de');const n=Number(code);
 if(n===0)return de?'Klar':'Clear';if([1,2].includes(n))return de?'Leicht bewölkt':'Partly cloudy';if(n===3)return de?'Bewölkt':'Cloudy';if([45,48].includes(n))return de?'Nebel':'Fog';if(n>=51&&n<=57)return de?'Nieselregen':'Drizzle';if(n>=61&&n<=67)return de?'Regen':'Rain';if(n>=71&&n<=77)return de?'Schnee':'Snow';if(n>=80&&n<=82)return de?'Regenschauer':'Rain showers';if([85,86].includes(n))return de?'Schneeschauer':'Snow showers';if(n>=95)return de?'Gewitter':'Thunderstorm';return de?'Wetter':'Weather';
}
export function weatherGlyph(code){const n=Number(code);if(n===0)return'☀️';if([1,2].includes(n))return'🌤️';if(n===3)return'☁️';if([45,48].includes(n))return'🌫️';if(n>=71&&n<=77||[85,86].includes(n))return'🌨️';if(n>=95)return'⛈️';if(n>=51&&n<=67||n>=80&&n<=82)return'🌧️';return'🌦️'}
export const value=(input,suffix='')=>input===null||input===undefined?'–':`${input}${suffix}`;
