import i18n from './i18n';

const de={
  routineLearning:'FamilyOS lernt aus euren Erledigungen, wann diese Routine typischerweise wieder ansteht.',
  routineLearningShort:'Lernt noch aus euren Erledigungen',
  routineUsually:'Meist etwa alle {{days}} Tage',
  routineNext:'Nächstes Mal ungefähr {{date}}',
  routineDue:'Wahrscheinlich wieder dran',
  routineOverdue:'Üblicherweise wäre das inzwischen erledigt',
  routineUpcoming:'Voraussichtlich in {{count}} Tagen wieder relevant',
  shoppingTitle:'Wahrscheinlich bald wieder nötig',
  shoppingHint:'Basierend auf euren tatsächlich abgehakten Einkäufen – nichts wird automatisch hinzugefügt.',
  shoppingReason:'Etwa alle {{days}} Tage · zuletzt vor {{since}} Tagen gekauft',
  shoppingAdd:'Hinzufügen',
  shoppingAddAll:'Alle übernehmen',
  shoppingDismiss:'Diesen Vorschlag ausblenden',
  shoppingAdded:'{{name}} wurde zur Einkaufsliste hinzugefügt.',
  shoppingAddedAll:'{{count}} Vorschläge wurden übernommen.',
};
const en={
  routineLearning:'FamilyOS learns from your completions when this routine usually becomes relevant again.',
  routineLearningShort:'Still learning from your completions',
  routineUsually:'Usually about every {{days}} days',
  routineNext:'Next time around {{date}}',
  routineDue:'Probably due again',
  routineOverdue:'Usually this would have been done by now',
  routineUpcoming:'Likely relevant again in {{count}} days',
  shoppingTitle:'Probably needed again soon',
  shoppingHint:'Based on items you actually checked off – nothing is added automatically.',
  shoppingReason:'About every {{days}} days · last bought {{since}} days ago',
  shoppingAdd:'Add',
  shoppingAddAll:'Add all',
  shoppingDismiss:'Hide this suggestion',
  shoppingAdded:'{{name}} was added to the shopping list.',
  shoppingAddedAll:'{{count}} suggestions were added.',
};

i18n.addResourceBundle('de','translation',{predictionUi:de},true,true);
i18n.addResourceBundle('en','translation',{predictionUi:en},true,true);
