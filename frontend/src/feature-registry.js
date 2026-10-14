const defineFeature=(id,{detail=false,familyContext=false,queryParams=[]}={})=>Object.freeze({
  id,
  detail,
  familyContext,
  queryParams:Object.freeze([...queryParams]),
});

export const FEATURE_REGISTRY=Object.freeze([
  defineFeature('vehicles',{familyContext:true,queryParams:['vehicle']}),
  defineFeature('notes',{familyContext:true,queryParams:['note']}),
  defineFeature('documents',{detail:true}),
  defineFeature('board',{detail:true}),
  defineFeature('birthdays',{detail:true,familyContext:true,queryParams:['birthday']}),
  defineFeature('trips',{detail:true}),
  defineFeature('decisions',{detail:true}),
  defineFeature('wishlists',{detail:true,familyContext:true,queryParams:['wishlist']}),
  defineFeature('games',{detail:true,familyContext:true,queryParams:['game','task']}),
  defineFeature('home'),
  defineFeature('todo',{queryParams:['todo']}),
  defineFeature('tasks',{familyContext:true,queryParams:['task']}),
  defineFeature('shopping',{queryParams:['mode','list','item']}),
  defineFeature('routines',{familyContext:true,queryParams:['routine']}),
  defineFeature('baby',{familyContext:true}),
  defineFeature('pets',{familyContext:true}),
  defineFeature('more'),
  defineFeature('settings',{detail:true}),
  defineFeature('calendar'),
  defineFeature('weather',{detail:true}),
  defineFeature('statistics',{detail:true,familyContext:true,queryParams:['stats_range','stats_view','stats_member','stats_domain','stats_from','stats_to']}),
  defineFeature('expenses',{detail:true,queryParams:['ledger','expense']}),
  defineFeature('contracts',{detail:true,familyContext:true}),
  defineFeature('inbox',{detail:true}),
  defineFeature('integrations',{detail:true,queryParams:['integration_connected','integration_error']}),
  defineFeature('members',{detail:true}),
  defineFeature('profile',{detail:true}),
  defineFeature('automations',{detail:true}),
  defineFeature('notifications',{detail:true}),
  defineFeature('loyalty',{detail:true}),
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
