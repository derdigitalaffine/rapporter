import {switchAppLanguage as switchLanguage} from './language-options';
import OfflineSyncStatus from './OfflineSyncStatus';
import {clearTracking} from './vehicle-tracking';
import './vehicles-i18n';
import {setCreateRankingIdentity} from './create-ranking-client';
import {RecurringWorkspace as RoutinesHub} from './TodoHub';
import TodoHub from './TodoHub';
import {startTransition,useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import useAppViewport from './use-app-viewport';
import {useTranslation} from 'react-i18next';
import './session-i18n';
import './prediction-i18n';
import './entitlements-i18n';
import './more-i18n';
import {api,isAuthenticated,login,logout} from './api';
import {Icon} from './icons';
import {TasksWorkspace as SmartTasks} from './TodoHub';
import SmartShoppingPredicted from './ShoppingPredictions';
import Messenger from './Messenger';
import CalendarHub from './CalendarHub';
import TodayHome from './TodayHome';
import GlobalCreate from './GlobalCreate';
import {useCreateActions} from './useCreateActions';
import './birthday-i18n';
import './profile-i18n';
import ProgramInfo from './ProgramInfo';
import './baby-i18n';
import './pet-i18n';
import MemberAvatar from './MemberAvatar';
import {DeferredModule,FeatureAvailabilityContext,FEATURE_COMPONENTS} from './FeatureModule';
import {acceptsFamilyContext,isDetailPage} from './feature-registry';
import {useFamilyPermissions} from './family-permissions';
import {toast} from './feedback';
import {APP_PAGES,pageFromLocation,pageHref} from './navigation';
import {pageIcon,pageLabel,primaryNavCurrent,primaryNavItems,primaryNavLabel} from './app-navigation';
import './family-context.css';
import './create-fab.css';
import './entitlements.css';
import './more-navigation.css';

const {vehicles:VehiclesHub,integrations:IntegrationHub,members:FamilyMembers,automations:AutomationHub,notifications:NotificationSettings,loyalty:LoyaltyCards,notes:NotesHub,documents:DocumentsHub,weather:WeatherHub,expenses:ExpensesHub,statistics:StatisticsHub,contracts:ContractsHub,decisions:DecisionsHub,games:GamesHub,wishlists:WishlistsHub,birthdays:BirthdaysHub,profile:ProfilePage,board:BoardHub,trips:TravelHub,baby:PregnancyBabyHub,pets:PetCareHub,settings:SettingsHub}=FEATURE_COMPONENTS;
const loadCreateFlowHost=()=>import('./CreateFlowHost.jsx');

const demo={tasks:[],task_lists:[],events:[],routines:[],shopping_lists:[],inbox_count:0,automation_count:0};
const ACTIVE_FAMILY_KEY='famuhle-active-family';
const unwrap=x=>x?.results||x||[];
const sameFamily=(row,familyId)=>String(row?.family||'')===String(familyId||'');
const unreadChats=rows=>(rows||[]).reduce((sum,row)=>sum+(Number(row?.unread)||0),0);
function scopedDashboard(raw,familyId,inboxRows=[],rules=[]){return {...raw,tasks:(raw.tasks||[]).filter(row=>sameFamily(row,familyId)),task_lists:(raw.task_lists||[]).filter(row=>sameFamily(row,familyId)),events:(raw.events||[]).filter(row=>sameFamily(row,familyId)),routines:(raw.routines||[]).filter(row=>sameFamily(row,familyId)),shopping_lists:(raw.shopping_lists||[]).filter(row=>sameFamily(row,familyId)),inbox_count:inboxRows.filter(row=>sameFamily(row,familyId)&&row.status==='new').length,automation_count:rules.filter(row=>sameFamily(row,familyId)&&row.enabled).length}}
function Card({children,className=''}){return <section className={`card ${className}`}>{children}</section>}
function Empty({text}){return <div className="empty">{text}</div>}
function PageHead({title}){return <div className="page-head"><h1>{title}</h1></div>}

function Login({onDone,expired=false}){const {t,i18n}=useTranslation();const [username,setUsername]=useState('');const [password,setPassword]=useState('');const [error,setError]=useState(false);const [busy,setBusy]=useState(false);async function submit(e){e.preventDefault();setError(false);setBusy(true);try{await login(username,password);onDone()}catch{setError(true)}finally{setBusy(false)}}return <main className="login-shell"><img className="brand-wide" src="/brand/logo-primary.svg" alt="FamilyOS"/><Card className="login-card">{expired&&<div className="integration-notice" role="status"><Icon name="info"/><div><strong>{t('sessionUi.expiredTitle')}</strong><span>{t('sessionUi.expiredMessage')}</span></div></div>}<h1>{t('login')}</h1><form onSubmit={submit}><label>{t('username')}<input value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username" required autoFocus/></label><label>{t('password')}<input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" required/></label>{error&&<p className="error" role="alert">{t('loginFailed')}</p>}<button className="primary" type="submit" disabled={busy}>{busy?t('pleaseWait'):t('login')}</button></form><button className="text-button" onClick={()=>switchLanguage(i18n)}><Icon name="language"/> Deutsch · English · Français · Nederlands · ไทย</button></Card></main>}
function DataState({t,error,onRetry}){if(error)return <div className="smart-empty app-load-state" role="alert"><Icon name="warning" size={34}/><strong>{t('sessionUi.loadFailed')}</strong><span>{error}</span><button className="secondary compact" onClick={onRetry}><Icon name="refresh"/>{t('sessionUi.retry')}</button></div>;return <div className="smart-empty app-load-state" role="status"><Icon name="refresh" size={34}/><strong>{t('sessionUi.loading')}</strong></div>}

export default function App(){
 const {t,i18n}=useTranslation();const queryAtBoot=new URLSearchParams(location.search);const integrationCallbackAtBoot=queryAtBoot.has('integration_connected')||queryAtBoot.has('integration_error');const initial=pageFromLocation();const [authed,setAuthed]=useState(isAuthenticated());const [sessionExpired,setSessionExpired]=useState(false);const [sessionUser,setSessionUser]=useState(null);const [active,setActive]=useState(initial);const [data,setData]=useState(demo);const [families,setFamilies]=useState([]);const [activeFamilyId,setActiveFamilyId]=useState(()=>localStorage.getItem(ACTIVE_FAMILY_KEY)||'');const activeFamilyIdRef=useRef(activeFamilyId);const loadRevisionRef=useRef(0);const [loading,setLoading]=useState(false);const [loaded,setLoaded]=useState(false);const [loadError,setLoadError]=useState('');const [installPrompt,setInstallPrompt]=useState(null);const [createFlow,setCreateFlow]=useState(null);const [createRevision,setCreateRevision]=useState(0);const [babyModule,setBabyModule]=useState(null);const [petModule,setPetModule]=useState(null);const [entitlements,setEntitlements]=useState(null);const [,setMessengerUnread]=useState(0);const family=families.find(row=>String(row.id)===String(activeFamilyId))||families[0];const currentMember=family?.memberships?.find(row=>String(row.user)===String(sessionUser?.id));const {role}=useFamilyPermissions(family);
 const createActions=useCreateActions({userId:sessionUser?.id,page:active,family:authed&&loaded?family:null,role,entitlements});
 useAppViewport(authed);
 function commitActiveFamilyId(nextId){const value=String(nextId||'');activeFamilyIdRef.current=value;setActiveFamilyId(value)}
 function invalidateLoads(){loadRevisionRef.current+=1}
 function canLeave(detail={}){const event=new CustomEvent('famuhle:before-navigation',{cancelable:true,detail});window.dispatchEvent(event);if(event.defaultPrevented){toast(t('notes:pendingNavigation'),{type:'info'});return false}return true}
 function navigate(next,{replace=false}={}){if(!canLeave({page:next}))return false;const page=APP_PAGES.has(next)?next:'home';const href=pageHref(page);const current=`${location.pathname}${location.search}${location.hash}`;if(href!==current){const method=replace?'replaceState':'pushState';history[method]({page,appNavigation:!replace},'',href)}startTransition(()=>setActive(page));return true}
 function backTo(fallback='more'){if(history.state?.appNavigation)history.back();else navigate(fallback,{replace:true})}
 async function load(requestedFamilyId=activeFamilyIdRef.current){if(!isAuthenticated())return;const revision=++loadRevisionRef.current;const isCurrent=()=>revision===loadRevisionRef.current;setLoading(true);setLoadError('');try{const session=await api('/auth/session/');if(!isCurrent())return;setCreateRankingIdentity(session.user?.id);setSessionUser(session.user||null);if(session.user?.is_superadmin){setFamilies([]);commitActiveFamilyId('');setData(demo);setBabyModule(null);setPetModule(null);setEntitlements(null);setMessengerUnread(0);setLoaded(true);return}const familyRows=unwrap(await api('/families/'));if(!isCurrent())return;setFamilies(familyRows);const preferred=(acceptsFamilyContext(pageFromLocation())?new URLSearchParams(location.search).get('family'):null)||requestedFamilyId||activeFamilyIdRef.current||localStorage.getItem(ACTIVE_FAMILY_KEY);const selected=familyRows.find(row=>String(row.id)===String(preferred))||familyRows[0];if(!selected){commitActiveFamilyId('');setData(demo);setBabyModule(null);setPetModule(null);setEntitlements(null);setMessengerUnread(0);localStorage.removeItem(ACTIVE_FAMILY_KEY);setLoaded(true);return}const selectedId=String(selected.id);commitActiveFamilyId(selectedId);localStorage.setItem(ACTIVE_FAMILY_KEY,selectedId);const [d,inbox,rules,babyState,petState,entitlementState,chatState]=await Promise.all([api(`/dashboard/?family=${encodeURIComponent(selectedId)}`),api('/inbox/').catch(()=>[]),api('/automation-rules/').catch(()=>[]),api(`/baby/module/?family=${encodeURIComponent(selectedId)}`).catch(()=>null),api(`/pets/module/?family=${encodeURIComponent(selectedId)}`).catch(()=>null),api(`/entitlements/?family=${encodeURIComponent(selectedId)}`).catch(()=>null),api('/chat/conversations/').catch(()=>({results:[]}))]);if(!isCurrent())return;setData(scopedDashboard(d,selectedId,unwrap(inbox),unwrap(rules)));setBabyModule(babyState);setPetModule(petState);setEntitlements(entitlementState);setMessengerUnread(unreadChats(chatState?.results));setLoaded(true)}catch(e){if(!isCurrent())return;if(e.message==='unauthorized')setAuthed(false);else setLoadError(e.message||t('sessionUi.loadFailed'))}finally{if(isCurrent())setLoading(false)}}
 useEffect(()=>{if(authed)load();const install=e=>{e.preventDefault();setInstallPrompt(e)};window.addEventListener('beforeinstallprompt',install);return()=>{invalidateLoads();window.removeEventListener('beforeinstallprompt',install)}},[authed]);
 useEffect(()=>{const reauth=()=>{setSessionExpired(true);setAuthed(false)};window.addEventListener('familyos:request-reauth',reauth);return()=>window.removeEventListener('familyos:request-reauth',reauth)},[]);
 useEffect(()=>{const expired=()=>{invalidateLoads();clearTracking();setSessionExpired(true);setSessionUser(null);setMessengerUnread(0);setAuthed(false)};window.addEventListener('famuhle:session-expired',expired);return()=>window.removeEventListener('famuhle:session-expired',expired)},[]);
 useEffect(()=>{const pop=()=>{if(!canLeave({popstate:true}))return;startTransition(()=>setActive(pageFromLocation()));setCreateFlow(null)};window.addEventListener('popstate',pop);return()=>window.removeEventListener('popstate',pop)},[]);
 useEffect(()=>{if(integrationCallbackAtBoot)queueMicrotask(()=>history.replaceState({page:'integrations'},'',pageHref('integrations')))},[]);
 if(!authed)return <Login expired={sessionExpired} onDone={()=>{setSessionExpired(false);setSessionUser(null);setLoaded(false);setLoadError('');setAuthed(true)}}/>;
 const signOut=async()=>{if(!canLeave({logout:true}))return;setAuthed(false);try{await logout()}catch(error){toast(error.message,{type:'error'})}invalidateLoads();clearTracking();setSessionUser(null);setFamilies([]);setBabyModule(null);setPetModule(null);setEntitlements(null);setMessengerUnread(0);setLoaded(false);navigate('home',{replace:true});setSessionExpired(false);setAuthed(false)};
 if(loaded&&sessionUser?.is_superadmin)return <main className="login-shell"><img className="brand-wide" src="/brand/logo-primary.svg" alt="FamilyOS"/><Card className="login-card"><small>Getrennte Administration</small><h1>Superadmin ist eine eigene PWA</h1><p>Das Admin-Cockpit verwendet eine getrennte Anmeldung und wird nicht innerhalb der FamilyOS-App geöffnet.</p><a className="primary" href="/superadmin/">Superadmin-PWA öffnen</a><button className="secondary" type="button" onClick={signOut}>FamilyOS-Anmeldung abmelden</button></Card></main>;
 async function switchFamily(nextId){if(!nextId||String(nextId)===String(family?.id))return;if(!canLeave({family:nextId}))return;localStorage.setItem(ACTIVE_FAMILY_KEY,String(nextId));commitActiveFamilyId(nextId);setCreateFlow(null);setCreateRevision(0);setBabyModule(null);setPetModule(null);setEntitlements(null);navigate('home');setData(demo);setLoaded(false);await load(String(nextId))}
 async function installApp(){if(!installPrompt)return;await installPrompt.prompt();try{await installPrompt.userChoice}finally{setInstallPrompt(null)}}
 async function toggleTask(x){try{await api(`/tasks/${x.id}/toggle/`,{method:'POST'});load()}catch(e){toast(e.message||t('saveFailed'),{type:'error'})}}

 function showOnboarding(){if(family?.id)localStorage.removeItem(`famuhle-onboarding-dismissed:${family.id}`);navigate('home')}
 function openCreate(id,context={}){if(!canLeave({create:id}))return;const href=`${location.pathname}${location.search}${location.hash}`;history.pushState({...history.state,createFlow:id},'',href);setCreateFlow({id,context})}
 function closeCreate(){if(history.state?.createFlow)history.back();else setCreateFlow(null)}
 async function refreshAfterCreate(){await load();setCreateRevision(value=>value+1)}
 const detail=isDetailPage(active);const familyKey=family?.id||'none';const contentKey=`${familyKey}-${createRevision}`;
 const pages={statistics:<StatisticsHub key={`statistics-${contentKey}`} family={family} role={role} entitlements={entitlements} onBack={()=>backTo('more')}/>,vehicles:<VehiclesHub key={`vehicles-${contentKey}`} family={family} userId={sessionUser?.id} onBack={()=>backTo('more')}/>,notes:<NotesHub key={`notes-${contentKey}`} family={family} onBack={()=>backTo('home')}/>,documents:<DocumentsHub key={`documents-${contentKey}`} family={family} onBack={()=>backTo('more')}/>,board:<BoardHub key={`board-${contentKey}`} family={family} onBack={()=>backTo('more')}/>,trips:<TravelHub key={`trips-${contentKey}`} family={family} onBack={()=>backTo('more')} onOpen={navigate}/>,decisions:<DecisionsHub key={`decisions-${contentKey}`} family={family} onBack={()=>backTo('more')}/>,games:<GamesHub key={`games-${contentKey}`} family={family} onBack={()=>backTo(new URLSearchParams(location.search).has('task')?'tasks':'more')}/>,wishlists:<WishlistsHub key={`wishlists-${contentKey}`} family={family} onBack={()=>backTo('more')} onCreate={openCreate}/>,home:<TodayHome createActions={createActions} createSuppressed={Boolean(createFlow)} key={`home-${contentKey}`} data={data} family={family} t={t} onTask={toggleTask} open={navigate} onCreate={openCreate}/>,todo:<TodoHub key={`todo-${contentKey}`} family={family} data={data} onCreate={openCreate}/>,tasks:<SmartTasks key={`tasks-${contentKey}`} family={family} currentUserId={sessionUser?.id} onChanged={load}/>,shopping:<SmartShoppingPredicted key={`shopping-${contentKey}`} family={family} onChanged={load}/>,routines:<RoutinesHub key={`routines-${contentKey}`} family={family} userId={sessionUser?.id} onChanged={load}/>,baby:<PregnancyBabyHub key={`baby-${contentKey}`} family={family} onBack={()=>backTo('more')} onModuleChange={setBabyModule}/>,pets:<PetCareHub key={`pets-${contentKey}`} family={family} onBack={()=>backTo('more')} onModuleChange={setPetModule}/>,more:<MorePage key={`more-${contentKey}`} family={family} families={families} role={role} data={data} t={t} i18n={i18n} open={navigate} babyModule={babyModule} petModule={petModule} entitlements={entitlements} onShowOnboarding={showOnboarding} onLogout={signOut} installable={!!installPrompt} onInstall={installApp} onSwitchFamily={switchFamily} loading={loading}/>,settings:<SettingsHub key={`settings-${contentKey}`} open={navigate}/>,calendar:<CalendarHub key={`calendar-${contentKey}`} family={family} t={t} onBack={()=>backTo('more')}/>,weather:<WeatherHub key={`weather-${contentKey}`} family={family} t={t} onBack={()=>backTo('home')}/>,birthdays:<BirthdaysHub key={`birthdays-${contentKey}`} family={family} onBack={()=>backTo('more')}/>,expenses:<ExpensesHub key={`expenses-${contentKey}`} entitlements={entitlements} family={family} onBack={()=>backTo('more')}/>,contracts:<ContractsHub key={`contracts-${contentKey}`} family={family} onBack={()=>backTo('more')} onCreate={openCreate}/>,inbox:<Messenger key={`messenger-${sessionUser?.id}-${familyKey}`} family={family} userId={sessionUser?.id} onBack={()=>backTo(family?'more':'inbox')} onChanged={load} onUnreadChange={setMessengerUnread} onLogout={signOut}/>,integrations:<IntegrationHub key={`integrations-${contentKey}`} family={family} onBack={()=>backTo('more')}/>,automations:<AutomationHub key={`automations-${contentKey}`} family={family} onBack={()=>backTo('more')}/>,members:<FamilyMembers key={`members-${contentKey}`} family={family} onBack={()=>backTo('more')}/>,profile:<ProfilePage key={`profile-${contentKey}`} family={family} onBack={()=>backTo('more')} onChanged={load}/>,notifications:<NotificationSettings key={`notifications-${contentKey}`} family={family} t={t} onBack={()=>backTo('more')}/>,loyalty:<LoyaltyCards key={`loyalty-${contentKey}`} family={family} onBack={()=>backTo('more')}/>};
 const babyInNav=babyModule?.enabled&&babyModule?.authorized&&babyModule?.show_in_main_navigation&&(!entitlements||entitlements.capabilities?.includes('pregnancy_baby'));const petInNav=petModule?.enabled&&petModule?.authorized&&petModule?.show_in_main_navigation&&(!entitlements||entitlements.capabilities?.includes('pets'));const nav=primaryNavItems(t,i18n,{baby:babyInNav,pet:petInNav});const currentNav=primaryNavCurrent(active,nav);const createContext={taskListId:data.task_lists?.[0]?.id||'',shoppingListId:data.shopping_lists?.[0]?.id||''};
 const headerTitle=pageLabel(active,t,i18n);
 return <FeatureAvailabilityContext.Provider value={{entitlements,role,babyModule,petModule}}><div className={`app-shell ${active==='inbox'?'messenger-shell':''} ${loaded&&family&&role&&active!=='inbox'&&active!=='settings'?'global-create-enabled':''}`} data-primary-nav={loaded&&family&&!detail?'true':'false'}><header className="topbar"><div className="brand-mini" role="heading" aria-level="1"><span>{headerTitle}</span></div><div className="topbar-context"><OfflineSyncStatus family={family}/>{currentMember&&<button className="profile-shortcut" onClick={()=>navigate('profile')} aria-label={t('profileUi.title')}><MemberAvatar person={currentMember} size={34} decorative/></button>}</div></header><main key={`${familyKey}-${active}`} className="content page-transition" data-page={active}>{loading&&loaded&&<div className="loading" role="status"><Icon name="refresh"/> {t('syncing')}</div>}{!loaded?<DataState t={t} error={loadError} onRetry={()=>load()}/>:family?pages[active]:pages.inbox}</main>{loaded&&family&&!detail&&createPortal(<nav className={`bottom-nav ${nav.length>6?'bottom-nav--dense':''}`} aria-label={primaryNavLabel(i18n)} style={{'--bottom-nav-items':nav.length}}>{nav.map(({id,icon,label})=><button key={id} className={currentNav===id?'active':''} onClick={()=>navigate(id)} aria-current={currentNav===id?'page':undefined} title={label}><Icon name={icon} size={21}/><span>{label}</span></button>)}</nav>,document.body)}{loaded&&family&&<GlobalCreate createActions={createActions} page={active} family={family} role={role} context={createContext} onCreate={openCreate} suppressed={Boolean(createFlow)||active==='inbox'||active==='settings'}/>}{createFlow&&<DeferredModule load={loadCreateFlowHost} onBack={closeCreate} userId={sessionUser?.id} action={createFlow?.id} family={family} data={data} context={createFlow?.context} onClose={closeCreate} onRefresh={refreshAfterCreate}/>}</div></FeatureAvailabilityContext.Provider>
}

const MORE_SECTION_IDS=['family','organisation','administration'];
function readStoredList(key){try{const value=JSON.parse(localStorage.getItem(key)||'[]');return Array.isArray(value)?value:[]}catch{return []}}
function normalizeMoreSectionOrder(order){const known=order.filter(id=>MORE_SECTION_IDS.includes(id));return [...new Set([...known,...MORE_SECTION_IDS])]}
function MoreSection({id,title,collapsed,customizing,dragging,dropTarget,onToggle,onDragStart,onDragOver,onDrop,onDragEnd,onPointerDown,onPointerMove,onPointerUp,onKeyDown,dragLabel,children}){const panelId=`more-section-${id}`;return <section className={`more-section ${collapsed?'collapsed':''} ${dragging?'is-dragging':''} ${dropTarget?'more-section-drop-target':''}`} data-more-section={id} onDragOver={customizing?event=>onDragOver(event,id):undefined} onDrop={customizing?event=>onDrop(event,id):undefined}><div className="section-title more-section-title"><h2><button type="button" className="more-section-toggle" data-more-toggle={id} onClick={()=>onToggle(id)} aria-expanded={!collapsed} aria-controls={panelId}>{title}<Icon name="next" size={15}/></button></h2>{customizing&&<button type="button" className="more-section-drag" data-more-drag-handle={id} draggable onDragStart={event=>onDragStart(event,id)} onDragEnd={onDragEnd} onPointerDown={event=>onPointerDown(event,id)} onPointerMove={event=>onPointerMove(event,id)} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onKeyDown={event=>onKeyDown(event,id)} aria-label={dragLabel} title={dragLabel}><Icon name="drag"/></button>}</div><div id={panelId} hidden={collapsed}><Card>{children}</Card></div></section>}

function MorePage({family,families,role,data,t,i18n,open,babyModule,petModule,entitlements,onShowOnboarding,onLogout,installable,onInstall,onSwitchFamily,loading}){
 const capabilities=new Set(entitlements?.capabilities||[]);
 const hasCapability=key=>!entitlements||capabilities.has(key);
 const familyId=family?.id||'none';
 const orderKey=`famuhle-more-section-order:v1:${familyId}`;
 const collapsedKey=`famuhle-more-section-collapsed:v1:${familyId}`;
 const [sectionOrder,setSectionOrder]=useState(()=>normalizeMoreSectionOrder(readStoredList(orderKey)));
 const [collapsedSections,setCollapsedSections]=useState(()=>new Set(readStoredList(collapsedKey).filter(id=>MORE_SECTION_IDS.includes(id))));
 const [customizing,setCustomizing]=useState(false);
 const [announcement,setAnnouncement]=useState('');
 const dragRef=useRef('');
 const [dragging,setDragging]=useState('');
 const [dropTarget,setDropTarget]=useState('');
 const babyAvailable=babyModule?.can_manage||(babyModule?.enabled&&babyModule?.authorized);
 const petAvailable=petModule?.can_manage||(petModule?.enabled&&petModule?.authorized);
 const babyInMainNav=babyModule?.enabled&&babyModule?.authorized&&babyModule?.show_in_main_navigation&&hasCapability('pregnancy_baby');
 const petInMainNav=petModule?.enabled&&petModule?.authorized&&petModule?.show_in_main_navigation&&hasCapability('pets');
 const familyItems=[
  ['board',pageLabel('board',t,i18n),pageIcon('board'),'',null],
  ['birthdays',pageLabel('birthdays',t,i18n),pageIcon('birthdays'),'',null],
  ...(babyAvailable&&!babyInMainNav?[['baby',pageLabel('baby',t,i18n),pageIcon('baby'),'','pregnancy_baby']]:[]),
  ...(petAvailable&&!petInMainNav?[['pets',pageLabel('pets',t,i18n),pageIcon('pets'),'','pets']]:[]),
  ['trips',pageLabel('trips',t,i18n),pageIcon('trips'),'','travel'],
  ['decisions',pageLabel('decisions',t,i18n),pageIcon('decisions'),'',null],
  ['wishlists',pageLabel('wishlists',t,i18n),pageIcon('wishlists'),'',null],
  ['games',pageLabel('games',t,i18n),pageIcon('games'),'',null],
 ];
 const organisationItems=[
  ['expenses',pageLabel('expenses',t,i18n),pageIcon('expenses'),'','expenses'],
  ...(role!=='guest'?[['statistics',pageLabel('statistics',t,i18n),pageIcon('statistics'),'','statistics']]:[]),
  ['contracts',pageLabel('contracts',t,i18n),pageIcon('contracts'),'',null],
  ['documents',pageLabel('documents',t,i18n),pageIcon('documents'),'',null],
  ['loyalty',pageLabel('loyalty',t,i18n),pageIcon('loyalty'),'',null],
  ...(['owner','adult'].includes(role)?[['vehicles',pageLabel('vehicles',t,i18n),pageIcon('vehicles'),'','vehicles']]:[]),
 ];
 const administrationItems=[
  ['profile',pageLabel('profile',t,i18n),pageIcon('profile'),'',null],
  ['settings',pageLabel('settings',t,i18n),pageIcon('settings'),'',null],
  ['members',pageLabel('members',t,i18n),pageIcon('members'),'',null],
  ['notifications',pageLabel('notifications',t,i18n),pageIcon('notifications'),'',null],
  ['integrations',pageLabel('integrations',t,i18n),pageIcon('integrations'),'',null],
  ['automations',pageLabel('automations',t,i18n),pageIcon('automations'),data.automation_count||'',null],
 ];
 const tier=entitlements?.display_name||entitlements?.tier||'';
 const lockedAction=label=>toast(t('entitlementsUi.lockedMessage',{feature:label,tier:tier||'Light'}),{type:'info'});
 const renderItem=([id,label,icon,count,capability])=>{const locked=Boolean(capability&&entitlements&&!hasCapability(capability));return <button className={`menu-row ${locked?'entitlement-locked':''}`} key={id} onClick={()=>locked&&id!=='statistics'?lockedAction(label):open(id)} aria-label={locked?`${label}. ${t('entitlementsUi.lockedLabel')}`:undefined}><Icon name={icon}/><span>{label}</span><span className="menu-tail">{locked?<span className="entitlement-lock-badge"><Icon name="lock" size={13}/>{t('entitlementsUi.lockedLabel')}</span>:count?<b className="count-badge">{count}</b>:null}{!locked&&<Icon name="next"/>}</span></button>};
 const titles={family:t('moreUi.family'),organisation:t('moreUi.householdFinance'),administration:t('moreUi.administration')};
 const content={family:familyItems.map(renderItem),organisation:organisationItems.map(renderItem),administration:<><button className="menu-row" onClick={onShowOnboarding}><Icon name="progress"/><span><strong>{t('onboarding.setupMenu')}</strong><small>{t('onboarding.setupMenuHint')}</small></span><Icon name="next"/></button>{administrationItems.map(renderItem)}</>};
 function saveOrder(next){localStorage.setItem(orderKey,JSON.stringify(next));return next}
 function announcePosition(id,order){const position=order.indexOf(id)+1;setAnnouncement(t('moreUi.moved',{title:titles[id],position,total:order.length}))}
 function reorderSection(source,target){if(!source||!target||source===target)return;setSectionOrder(current=>{const from=current.indexOf(source);const to=current.indexOf(target);if(from<0||to<0)return current;const next=current.slice();next.splice(from,1);next.splice(to,0,source);saveOrder(next);announcePosition(source,next);return next})}
 function toggleSection(id){setCollapsedSections(current=>{const next=new Set(current);if(next.has(id))next.delete(id);else next.add(id);localStorage.setItem(collapsedKey,JSON.stringify([...next]));return next})}
 function finishDrag(){dragRef.current='';setDragging('');setDropTarget('')}
 function toggleCustomizing(){finishDrag();setCustomizing(value=>!value)}
 function startDrag(event,id){dragRef.current=id;setDragging(id);event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain',id)}
 function dragOver(event,id){event.preventDefault();if(dragRef.current&&dragRef.current!==id)setDropTarget(id)}
 function drop(event,id){event.preventDefault();const source=event.dataTransfer.getData('text/plain')||dragRef.current;reorderSection(source,id);finishDrag()}
 function pointerDown(event,id){if(event.pointerType==='mouse'&&event.button!==0)return;dragRef.current=id;setDragging(id);event.currentTarget.setPointerCapture?.(event.pointerId)}
 function pointerMove(event,id){if(dragRef.current!==id)return;const target=document.elementFromPoint(event.clientX,event.clientY)?.closest?.('[data-more-section]')?.dataset.moreSection;if(target&&target!==id){setDropTarget(target);reorderSection(id,target)}}
 function pointerUp(event){if(event.currentTarget.hasPointerCapture?.(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);finishDrag()}
 function keyboardMove(event,id){if(event.key!=='ArrowUp'&&event.key!=='ArrowDown')return;event.preventDefault();setSectionOrder(current=>{const index=current.indexOf(id);const nextIndex=index+(event.key==='ArrowUp'?-1:1);if(index<0||nextIndex<0||nextIndex>=current.length)return current;const next=current.slice();[next[index],next[nextIndex]]=[next[nextIndex],next[index]];saveOrder(next);announcePosition(id,next);return next})}
 return <>
  {families.length>1&&<Card><label className="family-switcher" style={{maxWidth:'100%'}}><span className="sr-only">{t('members')}</span><Icon name="members" size={15}/><select value={family?.id||''} onChange={event=>onSwitchFamily(event.target.value)} disabled={loading}>{families.map(item=><option value={item.id} key={item.id}>{item.name}</option>)}</select></label></Card>}
  {entitlements&&<Card><div className="entitlement-summary"><div className="entitlement-summary-main"><Icon name={entitlements.tier==='light'?'lock':'check'}/><span><small>{t('entitlementsUi.access')}</small><strong>{tier}</strong></span></div><span className={`entitlement-tier ${entitlements.tier==='vip'?'vip':''}`}>{tier}</span></div><p className="entitlement-summary-hint">{t('entitlementsUi.tierHint')}</p></Card>}
  {installable&&<Card><button className="menu-row install-row" onClick={onInstall}><Icon name="install"/><span><strong>{t('installApp')}</strong><small>{t('pwaHint')}</small></span><Icon name="next"/></button></Card>}
  <div className="more-toolbar"><button type="button" className="secondary compact more-customize" data-more-customize aria-pressed={customizing} onClick={toggleCustomizing}><Icon name="settings" size={16}/>{customizing?t('moreUi.done'):t('moreUi.customize')}</button></div>
  <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
  {sectionOrder.map(id=><MoreSection key={id} id={id} title={titles[id]} collapsed={collapsedSections.has(id)} customizing={customizing} dragging={dragging===id} dropTarget={dropTarget===id} onToggle={toggleSection} onDragStart={startDrag} onDragOver={dragOver} onDrop={drop} onDragEnd={finishDrag} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onKeyDown={keyboardMove} dragLabel={t('moreUi.dragLabel',{title:titles[id]})}>{content[id]}</MoreSection>)}
  <Card><button className="menu-row" onClick={()=>switchLanguage(i18n)}><Icon name="language"/><span>{t('language')}</span><strong>{i18n.language.toUpperCase()}</strong></button><button className="menu-row danger-text" onClick={onLogout}><Icon name="logout"/><span>{t('logout')}</span></button></Card>
  <ProgramInfo/>
  {family&&<p className="family-note">{family.name} · {family.timezone}</p>}
 </>
}
