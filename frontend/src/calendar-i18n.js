import i18n from './i18n';

const de={
 officialSource:'Amtliche Ferientermine',agenda:'Familienagenda',familyCalendar:'Familienkalender',sources:'Kalenderquellen',showPast:'Vergangene anzeigen',hidePast:'Vergangene ausblenden',
 sourceFamily:'Familie',sourceBirthdays:'Geburtstage',sourceWarnings:'Warnungen',sourceWaste:'Müll',sourceWeather:'Wetter',sourceTransit:'ÖPNV',sourceSchool:'Schule',sourceCalendar:'Kalender',
 sourceHealthOne:'Eine Kalenderquelle braucht Aufmerksamkeit',sourceHealthMany:'{{count}} Kalenderquellen brauchen Aufmerksamkeit',sourceHealthOpen:'Integrationen öffnen',
 nextWaste:'Nächste Müllabfuhr',
 noSourceEntries:'Für diese Quelle gibt es aktuell keine Einträge.',showAllSources:'Alle Quellen zeigen',allDay:'Ganztägig',
 undatedUpper:'OHNE DATUM',todayUpper:'HEUTE',tomorrowUpper:'MORGEN',yesterdayUpper:'GESTERN',undated:'Ohne Datum',noDate:'Kein Datum',
 delay:'Verspätung',minutes:'Minuten',source:'Quelle',readonly:'Dieser Eintrag kommt aus einer verbundenen Quelle und ist hier schreibgeschützt.',
 listTools:'Listenwerkzeuge',listDensity:'Listendichte',densityNormal:'Normal',densityCompact:'Kompakt',selectEvents:'Auswählen',selectionDone:'Fertig',selectAllVisible:'Alle auswählbaren',clearSelection:'Auswahl aufheben',selectedCount:'{{count}} ausgewählt',selectEvent:'{{title}} auswählen',readonlySelection:'Nicht auswählbar: verbundener oder virtueller Kalendereintrag',deleteSelected:'Auswahl löschen',deleteSelectedTitle:'Ausgewählte Termine löschen?',deleteSelectedMessage:'Ausgewählt: {{count}}. Diese FamilyOS-Termine werden dauerhaft gelöscht. Verbundene Kalender bleiben unangetastet.',deleteSelectedSuccess:'Gelöscht: {{count}}.',deleteSelectedPartial:'Gelöscht: {{deleted}} · fehlgeschlagen: {{failed}}.',
 calendarIntro:'Alle Termine aus FamilyOS und verbundenen Kalendern an einem Ort.',calendarControls:'Kalender steuern',previousPeriod:'Vorheriger Zeitraum',nextPeriod:'Nächster Zeitraum',today:'Heute',chooseView:'Kalenderansicht wählen',viewWeek:'Woche',viewMonth:'Monat',viewList:'Liste',week:'Woche',free:'Frei',noEventsThisDay:'Keine Termine an diesem Tag.'
};
const en={
 officialSource:'Official holiday dates',agenda:'Family agenda',familyCalendar:'Family calendar',sources:'Calendar sources',showPast:'Show past',hidePast:'Hide past',
 sourceFamily:'Family',sourceBirthdays:'Birthdays',sourceWarnings:'Warnings',sourceWaste:'Waste',sourceWeather:'Weather',sourceTransit:'Transit',sourceSchool:'School',sourceCalendar:'Calendar',
 sourceHealthOne:'One calendar source needs attention',sourceHealthMany:'{{count}} calendar sources need attention',sourceHealthOpen:'Open integrations',
 nextWaste:'Next waste collections',
 noSourceEntries:'There are currently no entries for this source.',showAllSources:'Show all sources',allDay:'All day',
 undatedUpper:'NO DATE',todayUpper:'TODAY',tomorrowUpper:'TOMORROW',yesterdayUpper:'YESTERDAY',undated:'No date',noDate:'No date',
 delay:'Delay',minutes:'minutes',source:'Source',readonly:'This entry comes from a connected source and is read-only here.',
 listTools:'List tools',listDensity:'List density',densityNormal:'Normal',densityCompact:'Compact',selectEvents:'Select',selectionDone:'Done',selectAllVisible:'Select all eligible',clearSelection:'Clear selection',selectedCount:'{{count}} selected',selectEvent:'Select {{title}}',readonlySelection:'Not selectable: connected or virtual calendar entry',deleteSelected:'Delete selection',deleteSelectedTitle:'Delete selected events?',deleteSelectedMessage:'Selected: {{count}}. These FamilyOS events will be permanently deleted. Connected calendars stay untouched.',deleteSelectedSuccess:'Deleted: {{count}}.',deleteSelectedPartial:'Deleted: {{deleted}} · failed: {{failed}}.',
 calendarIntro:'FamilyOS and connected calendars, together in one place.',calendarControls:'Calendar controls',previousPeriod:'Previous period',nextPeriod:'Next period',today:'Today',chooseView:'Choose calendar view',viewWeek:'Week',viewMonth:'Month',viewList:'List',week:'Week',free:'Free',noEventsThisDay:'No events on this day.'
};

i18n.addResourceBundle('de','translation',{calendarUi:de},true,true);
i18n.addResourceBundle('en','translation',{calendarUi:en},true,true);