import i18n from './i18n';

const de={
 officialSource:'Amtliche Ferientermine',agenda:'Familienagenda',sources:'Kalenderquellen',showPast:'Vergangene anzeigen',hidePast:'Vergangene ausblenden',
 sourceFamily:'Familie',sourceWarnings:'Warnungen',sourceWaste:'Müll',sourceWeather:'Wetter',sourceTransit:'ÖPNV',sourceSchool:'Schule',sourceCalendar:'Kalender',
 nextWaste:'Nächste Müllabfuhr',
 noSourceEntries:'Für diese Quelle gibt es aktuell keine Einträge.',showAllSources:'Alle Quellen zeigen',allDay:'Ganztägig',
 undatedUpper:'OHNE DATUM',todayUpper:'HEUTE',tomorrowUpper:'MORGEN',yesterdayUpper:'GESTERN',undated:'Ohne Datum',noDate:'Kein Datum',
 delay:'Verspätung',minutes:'Minuten',source:'Quelle',readonly:'Dieser Eintrag kommt aus einer verbundenen Quelle und ist hier schreibgeschützt.'
};
const en={
 officialSource:'Official holiday dates',agenda:'Family agenda',sources:'Calendar sources',showPast:'Show past',hidePast:'Hide past',
 sourceFamily:'Family',sourceWarnings:'Warnings',sourceWaste:'Waste',sourceWeather:'Weather',sourceTransit:'Transit',sourceSchool:'School',sourceCalendar:'Calendar',
 nextWaste:'Next waste collections',
 noSourceEntries:'There are currently no entries for this source.',showAllSources:'Show all sources',allDay:'All day',
 undatedUpper:'NO DATE',todayUpper:'TODAY',tomorrowUpper:'TOMORROW',yesterdayUpper:'YESTERDAY',undated:'No date',noDate:'No date',
 delay:'Delay',minutes:'minutes',source:'Source',readonly:'This entry comes from a connected source and is read-only here.'
};

i18n.addResourceBundle('de','translation',{calendarUi:de},true,true);
i18n.addResourceBundle('en','translation',{calendarUi:en},true,true);