import i18n from './i18n';

const de={
 officialSource:'Amtliche Ferientermine',agenda:'Familienagenda',familyCalendar:'Familienkalender',sources:'Kalenderquellen',showPast:'Vergangene anzeigen',hidePast:'Vergangene ausblenden',
 sourceFamily:'Familie',sourceBirthdays:'Geburtstage',sourceWarnings:'Warnungen',sourceWaste:'Müll',sourceWeather:'Wetter',sourceTransit:'ÖPNV',sourceSchool:'Schule',sourceCalendar:'Kalender',
 nextWaste:'Nächste Müllabfuhr',noSourceEntries:'Für diese Quelle gibt es aktuell keine Einträge.',showAllSources:'Alle Quellen zeigen',allDay:'Ganztägig',
 undatedUpper:'OHNE DATUM',todayUpper:'HEUTE',tomorrowUpper:'MORGEN',yesterdayUpper:'GESTERN',undated:'Ohne Datum',noDate:'Kein Datum',
 delay:'Verspätung',minutes:'Minuten',source:'Quelle',readonly:'Dieser Eintrag kommt aus einer verbundenen Quelle und ist hier schreibgeschützt.',
 calendarIntro:'Alle Termine aus FamilyOS und verbundenen Kalendern an einem Ort.',calendarControls:'Kalender steuern',
 previousPeriod:'Vorheriger Zeitraum',nextPeriod:'Nächster Zeitraum',today:'Heute',chooseView:'Kalenderansicht wählen',viewWeek:'Woche',viewMonth:'Monat',viewList:'Liste',week:'Woche',
 newEvent:'Termin',free:'Frei',noEventsThisDay:'Keine Termine an diesem Tag.',recurring:'Wiederkehrend',person:'Person',
 customizeSources:'Quellen anpassen',appearanceSaved:'Kalenderdarstellung gespeichert.',color:'Farbe',symbol:'Symbol',
 color_blue:'Blau',color_teal:'Petrol',color_green:'Grün',color_amber:'Bernstein',color_orange:'Orange',color_red:'Rot',color_pink:'Rosa',color_purple:'Violett',color_slate:'Schiefer',
 icon_calendar:'Kalender',icon_school:'Schule',icon_waste:'Müll',icon_weather:'Wetter',icon_transit:'ÖPNV',icon_members:'Familie',icon_user:'Person',icon_heart:'Herz',icon_pet:'Haustier',icon_baby:'Kind',icon_location:'Ort',icon_clock:'Uhr',icon_tags:'Markierung',icon_info:'Info'
};
const en={
 officialSource:'Official holiday dates',agenda:'Family agenda',familyCalendar:'Family calendar',sources:'Calendar sources',showPast:'Show past',hidePast:'Hide past',
 sourceFamily:'Family',sourceBirthdays:'Birthdays',sourceWarnings:'Warnings',sourceWaste:'Waste',sourceWeather:'Weather',sourceTransit:'Transit',sourceSchool:'School',sourceCalendar:'Calendar',
 nextWaste:'Next waste collections',noSourceEntries:'There are currently no entries for this source.',showAllSources:'Show all sources',allDay:'All day',
 undatedUpper:'NO DATE',todayUpper:'TODAY',tomorrowUpper:'TOMORROW',yesterdayUpper:'YESTERDAY',undated:'No date',noDate:'No date',
 delay:'Delay',minutes:'minutes',source:'Source',readonly:'This entry comes from a connected source and is read-only here.',
 calendarIntro:'FamilyOS and connected calendars, together in one place.',calendarControls:'Calendar controls',previousPeriod:'Previous period',nextPeriod:'Next period',today:'Today',chooseView:'Choose calendar view',
 viewWeek:'Week',viewMonth:'Month',viewList:'List',week:'Week',newEvent:'Event',free:'Free',noEventsThisDay:'No events on this day.',recurring:'Recurring',person:'Person',
 customizeSources:'Customize sources',appearanceSaved:'Calendar appearance saved.',color:'Color',symbol:'Symbol',
 color_blue:'Blue',color_teal:'Teal',color_green:'Green',color_amber:'Amber',color_orange:'Orange',color_red:'Red',color_pink:'Pink',color_purple:'Purple',color_slate:'Slate',
 icon_calendar:'Calendar',icon_school:'School',icon_waste:'Waste',icon_weather:'Weather',icon_transit:'Transit',icon_members:'Family',icon_user:'Person',icon_heart:'Heart',icon_pet:'Pet',icon_baby:'Child',icon_location:'Location',icon_clock:'Clock',icon_tags:'Tag',icon_info:'Info'
};

i18n.addResourceBundle('de','translation',{calendarUi:de,saving:'Wird gespeichert …'},true,true);
i18n.addResourceBundle('en','translation',{calendarUi:en,saving:'Saving …'},true,true);