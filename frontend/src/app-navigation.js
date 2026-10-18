export const PRIMARY_NAV_IDS=Object.freeze(['home','todo','shopping','calendar','more']);

const PAGE_ICONS=Object.freeze({
  home:'home',
  'legacy-home':'history',
  todo:'tasks',
  tasks:'tasks',
  shopping:'shopping',
  calendar:'calendar',
  inbox:'inbox',
  more:'more',
  settings:'settings',
  profile:'user',
  notifications:'warning',
  integrations:'integrations',
  automations:'automation',
  members:'members',
  routines:'history',
  birthdays:'calendar',
  baby:'baby',
  pregnancy:'heart',
  pets:'pet',
  contracts:'receipt',
  loyalty:'store',
  vehicles:'route',
  trips:'route',
  decisions:'check',
  games:'members',
  wishlists:'heart',
  documents:'receipt',
  board:'inbox',
  weather:'weather',
  expenses:'receipt',
  statistics:'trend',
  notes:'receipt',
});

export function pageIcon(page){
  return PAGE_ICONS[page]||'info';
}

export function pageLabel(page,t,i18n){
  const english=i18n.language?.startsWith('en');
  const labels={
    home:t('today'),
    'legacy-home':t('moreUi.legacyHome'),
    todo:english?'Tasks':'Aufgaben',
    tasks:english?'Tasks':'Aufgaben',
    shopping:t('shopping'),
    calendar:t('calendar'),
    inbox:t('messengerUi.title'),
    more:t('more'),
    settings:english?'Settings':'Einstellungen',
    profile:t('profileUi.title'),
    notifications:t('notifications'),
    integrations:t('integrations'),
    automations:t('ifThen'),
    members:t('members'),
    routines:english?'Tasks':'Aufgaben',
    birthdays:t('birthdayUi.title'),
    baby:english?'Children':'Kinder',
    pregnancy:t('babyUi.pregnancy'),
    pets:t('petUi.title'),
    contracts:english?'Contracts':'Verträge',
    loyalty:t('loyaltyUi.title'),
    vehicles:t('vehiclesUi.title'),
    trips:english?'Trips':'Reisen',
    decisions:english?'Decisions':'Entscheidungen',
    games:english?'Games':'Spiele',
    wishlists:english?'Wishlists':'Wunschlisten',
    documents:english?'Documents':'Dokumente',
    board:english?'Pinboard':'Pinnwand',
    weather:english?'Weather':'Wetter',
    expenses:t('expensesUi.title'),
    statistics:t('statisticsUi.title'),
    notes:english?'Notes':'Notizen',
  };
  return labels[page]||'FamilyOS';
}

export function primaryNavItems(t,i18n,{baby=false,pet=false}={}){
  const ids=['home','todo','shopping','calendar',...(baby?['baby']:[]),...(pet?['pets']:[]),'more'];
  return ids.map(id=>({
    id,
    icon:pageIcon(id),
    label:id==='baby'?t('babyUi.short'):id==='pets'?t('petUi.short'):pageLabel(id,t,i18n),
  }));
}

export function primaryNavCurrent(page,items=PRIMARY_NAV_IDS){
  const ids=Array.isArray(items)?items.map(item=>typeof item==='string'?item:item.id):PRIMARY_NAV_IDS;
  if(['tasks','routines'].includes(page)&&ids.includes('todo'))return 'todo';
  return ids.includes(page)?page:'more';
}

export function primaryNavLabel(i18n){
  return i18n.language?.startsWith('en')?'Primary navigation':'Hauptnavigation';
}
