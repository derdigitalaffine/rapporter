import i18n from './i18n';

const de={
 title:'Dokumente',back:'Zurück',searchRegion:'Dokumente durchsuchen',search:'Dokumente durchsuchen',searchPlaceholder:'Titel, Text, Absender oder Referenz suchen …',filters:'Filter',activeFilters:'{{count}} aktive Filter',activeFilters_other:'{{count}} aktive Filter',type:'Typ',typePlaceholder:'z. B. insurance',person:'Person',visibility:'Sichtbarkeit',correspondent:'Absender / Korrespondent',correspondentPlaceholder:'z. B. AOK',dateFrom:'Datum von',dateTo:'Datum bis',pinned:'Angepinnt',all:'Alle',private:'Privat',family:'Familie',selected:'Ausgewählt',shared:'Geteilt',yes:'Ja',no:'Nein',reset:'Filter zurücksetzen',loading:'Suche …',resultCount:'{{count}} Dokument',resultCount_other:'{{count}} Dokumente',forQuery:'für „{{query}}“',loadFailed:'Dokumente konnten nicht geladen werden.',retry:'Erneut versuchen',empty:'Keine passenden Dokumente',emptyHint:'Passe Suchbegriff oder Filter an.',untitled:'Ohne Titel',open:'Öffnen',visibility_private:'Privat',visibility_family:'Familie',visibility_selected:'Ausgewählt'
};
const en={
 title:'Documents',back:'Back',searchRegion:'Search documents',search:'Search documents',searchPlaceholder:'Search title, text, sender or reference …',filters:'Filters',activeFilters:'{{count}} active filter',activeFilters_other:'{{count}} active filters',type:'Type',typePlaceholder:'e.g. insurance',person:'Person',visibility:'Visibility',correspondent:'Sender / correspondent',correspondentPlaceholder:'e.g. insurer',dateFrom:'Date from',dateTo:'Date to',pinned:'Pinned',all:'All',private:'Private',family:'Family',selected:'Selected',shared:'Shared',yes:'Yes',no:'No',reset:'Reset filters',loading:'Searching …',resultCount:'{{count}} document',resultCount_other:'{{count}} documents',forQuery:'for “{{query}}”',loadFailed:'Documents could not be loaded.',retry:'Try again',empty:'No matching documents',emptyHint:'Adjust your search or filters.',untitled:'Untitled',open:'Open',visibility_private:'Private',visibility_family:'Family',visibility_selected:'Selected'
};

i18n.addResourceBundle('de','documents',de);
i18n.addResourceBundle('en','documents',en);
