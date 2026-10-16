const defineFeature=(id,{detail=false,familyContext=false,queryParams=[],load=null,capability=null}={})=>Object.freeze({
  id,
  detail,
  familyContext,
  queryParams:Object.freeze([...(familyContext?['family']:[]),...queryParams]),
  load,
  capability,
});

export const FEATURE_REGISTRY=Object.freeze([
  defineFeature('vehicles',{familyContext:true,queryParams:['vehicle'],capability:'vehicles',load:()=>import('./VehiclesHub.jsx')}),
  defineFeature('notes',{familyContext:true,queryParams:['note'],load:()=>import('./NotesHub.jsx')}),
  defineFeature('documents',{detail:true,load:()=>import('./DocumentsHub.jsx')}),
  defineFeature('board',{detail:true,load:()=>import('./BoardHub.jsx')}),
  defineFeature('birthdays',{detail:true,familyContext:true,queryParams:['birthday'],load:()=>import('./BirthdaysHub.jsx')}),
  defineFeature('trips',{detail:true,capability:'travel',load:()=>import('./TravelHub.jsx')}),
  defineFeature('decisions',{detail:true,load:()=>import('./DecisionsHub.jsx')}),
  defineFeature('wishlists',{detail:true,familyContext:true,queryParams:['wishlist'],load:()=>import('./WishlistsHub.jsx')}),
  defineFeature('games',{detail:true,familyContext:true,queryParams:['game','task'],load:()=>import('./GamesHub.jsx')}),
  defineFeature('home'),
  defineFeature('todo',{queryParams:['todo']}),
  defineFeature('tasks',{familyContext:true,queryParams:['task']}),
  defineFeature('shopping',{queryParams:['mode','list','item']}),
  defineFeature('routines',{familyContext:true,queryParams:['routine']}),
  defineFeature('baby',{familyContext:true,capability:'pregnancy_baby',load:()=>import('./PregnancyBabyHub.jsx')}),
  defineFeature('pets',{familyContext:true,capability:'pets',load:()=>import('./PetCareHub.jsx')}),
  defineFeature('more'),
  defineFeature('settings',{detail:true,load:()=>import('./SettingsHub.jsx')}),
  defineFeature('calendar'),
  defineFeature('weather',{detail:true,load:()=>import('./WeatherHub.jsx')}),
  defineFeature('statistics',{detail:true,familyContext:true,capability:'statistics',queryParams:['stats_range','stats_view','stats_member','stats_domain','stats_from','stats_to'],load:()=>import('./StatisticsHub.jsx')}),
  defineFeature('expenses',{detail:true,capability:'expenses',queryParams:['ledger','expense'],load:()=>import('./ExpensesHub.jsx')}),
  defineFeature('contracts',{detail:true,familyContext:true,load:()=>import('./ContractsHub.jsx')}),
  defineFeature('inbox',{detail:true}),
  defineFeature('integrations',{detail:true,queryParams:['integration_connected','integration_error'],load:()=>import('./IntegrationHub.jsx')}),
  defineFeature('members',{detail:true,load:()=>import('./FamilyMembers.jsx')}),
  defineFeature('profile',{detail:true,load:()=>import('./ProfilePage.jsx')}),
  defineFeature('automations',{detail:true,load:()=>import('./AutomationHub.jsx')}),
  defineFeature('notifications',{detail:true,load:()=>import('./NotificationSettings.jsx')}),
  defineFeature('loyalty',{detail:true,load:()=>import('./LoyaltyCards.jsx')}),
]);

export const FEATURES_BY_ID=Object.freeze(Object.fromEntries(FEATURE_REGISTRY.map(feature=>[feature.id,feature])));
export const APP_PAGE_IDS=Object.freeze(FEATURE_REGISTRY.map(feature=>feature.id));
export const APP_PAGES=new Set(APP_PAGE_IDS);
export const DETAIL_PAGES=new Set(FEATURE_REGISTRY.filter(feature=>feature.detail).map(feature=>feature.id));
export const FAMILY_CONTEXT_PAGES=new Set(FEATURE_REGISTRY.filter(feature=>feature.familyContext).map(feature=>feature.id));
export const FEATURE_QUERY_PARAMS=new Set(FEATURE_REGISTRY.flatMap(feature=>feature.queryParams));

export const featureForPage=page=>FEATURES_BY_ID[page]||null;
export const isAppPage=page=>APP_PAGES.has(page);
export const isDetailPage=page=>DETAIL_PAGES.has(page);
export const acceptsFamilyContext=page=>FAMILY_CONTEXT_PAGES.has(page);
export const queryParamsForPage=page=>featureForPage(page)?.queryParams||[];

// UI loading guards only. Server/domain authorization remains authoritative.
export function featureAvailability(page,{entitlements=null,role=null,babyModule=null,petModule=null}={}){
  const feature=featureForPage(page);
  if(!feature)return 'unknown';
  if(page==='statistics'&&role==='guest')return 'denied';
  if(feature.capability&&entitlements&&!entitlements.capabilities?.includes(feature.capability))return 'locked';
  if(page==='statistics'&&!entitlements)return 'pending';
  const module=page==='baby'?babyModule:page==='pets'?petModule:null;
  if(module&&!module.can_manage&&(!module.enabled||!module.authorized))return 'denied';
  return 'available';
}
