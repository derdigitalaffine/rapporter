import i18n from './i18n';

const de={
 title:'Wetter',subtitle:'Aktuell und die nächsten 7 Tage',current:'Aktuell',forecast:'7-Tage-Vorhersage',details:'Tagesdetails',today:'Heute',
 feelsLike:'Gefühlt {{value}}',highLow:'{{min}} / {{max}}',precipProbability:'Regen {{value}}',precipitation:'Niederschlag',wind:'Wind',gusts:'Böen',sunrise:'Sonnenaufgang',sunset:'Sonnenuntergang',uv:'UV-Index',humidity:'Luftfeuchte',
 updated:'Zuletzt aktualisiert {{value}}',notCurrent:'Nicht aktuell',staleHint:'Die letzte erfolgreiche Vorhersage bleibt sichtbar. Die Wetterquelle konnte zuletzt nicht aktualisiert werden.',
 noData:'Noch keine Wetterdaten verfügbar.',noDataHint:'Verbinde oder synchronisiere eine Wetterquelle unter Integrationen.',openIntegrations:'Integrationen öffnen',retryHint:'FamilyOS ruft Wetterdaten serverseitig ab; ein erneuter Sync erfolgt über die Integration.',
 alerts:'Aktive Wetterwarnungen',validUntil:'Gültig bis {{value}}',from:'ab {{value}}',region:'Region',provider:'Quelle',
 condition:{clear:'Klar',mainlyClear:'Überwiegend klar',partlyCloudy:'Teilweise bewölkt',cloudy:'Bewölkt',fog:'Nebel',drizzle:'Nieselregen',rain:'Regen',snow:'Schnee',showers:'Schauer',thunderstorm:'Gewitter',unknown:'Wetterlage'},
};
const en={
 title:'Weather',subtitle:'Current conditions and the next 7 days',current:'Current',forecast:'7-day forecast',details:'Day details',today:'Today',
 feelsLike:'Feels like {{value}}',highLow:'{{min}} / {{max}}',precipProbability:'Rain {{value}}',precipitation:'Precipitation',wind:'Wind',gusts:'Gusts',sunrise:'Sunrise',sunset:'Sunset',uv:'UV index',humidity:'Humidity',
 updated:'Last updated {{value}}',notCurrent:'Not current',staleHint:'The last successful forecast remains available. The weather source could not be refreshed most recently.',
 noData:'No weather data yet.',noDataHint:'Connect or sync a weather source under Integrations.',openIntegrations:'Open integrations',retryHint:'FamilyOS fetches weather server-side; retry through the integration.',
 alerts:'Active weather warnings',validUntil:'Valid until {{value}}',from:'from {{value}}',region:'Region',provider:'Source',
 condition:{clear:'Clear',mainlyClear:'Mostly clear',partlyCloudy:'Partly cloudy',cloudy:'Cloudy',fog:'Fog',drizzle:'Drizzle',rain:'Rain',snow:'Snow',showers:'Showers',thunderstorm:'Thunderstorm',unknown:'Weather'},
};

i18n.addResourceBundle('de','translation',{weatherUi:de},true,true);
i18n.addResourceBundle('en','translation',{weatherUi:en},true,true);
