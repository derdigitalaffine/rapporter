import {useEffect,useRef,useState} from 'react';
import {api,AUTH_CHANGED_EVENT} from './api';
import {Icon} from './icons';

const POLL_MS=4000;
const denied=error=>[401,403,404].includes(error?.status)||error?.message==='unauthorized';
const text={
 de:{title:'Spiele',all:'Alle',loading:'Spiele werden geladen …',error:'Spiele konnten nicht geladen werden.',retry:'Erneut laden',stale:'Stand konnte nicht aktualisiert werden. Der letzte bestätigte Stand bleibt sichtbar.',denied:'Diese Spiele sind nicht mehr verfügbar.',saveError:'Aktion fehlgeschlagen. Bitte erneut versuchen.',empty:'Keine offenen Spiele',emptyHint:'Fordere ein Familienmitglied heraus.',invitation:'Einladung',waitingReply:'Antwort ausstehend',turn:'Du bist am Zug',waiting:'Wartet auf die andere Person',setup:'Flotte setzen',waitingFleet:'Wartet auf die gegnerische Flotte',active:'Spiel läuft',finished:'Zuletzt beendet',round:'Runde',open:'offen',rps:'Schere · Stein · Papier',battleship:'Schiffe versenken',quiz:'Quiz-Duell',connectFour:'Vier Gewinnt'},
 en:{title:'Games',all:'All',loading:'Loading games …',error:'Games could not be loaded.',retry:'Retry',stale:'Could not refresh. The last confirmed state remains visible.',denied:'These games are no longer available.',saveError:'Action failed. Please try again.',empty:'No open games',emptyHint:'Challenge a family member.',invitation:'Invitation',waitingReply:'Waiting for reply',turn:'Your turn',waiting:'Waiting for the other player',setup:'Place fleet',waitingFleet:'Waiting for opponent fleet',active:'Game in progress',finished:'Recently finished',round:'Round',open:'open',rps:'Rock · Paper · Scissors',battleship:'Battleship',quiz:'Quiz duel',connectFour:'Connect Four'},
 fr:{title:'Jeux',all:'Tous',loading:'Chargement des jeux…',error:'Impossible de charger les jeux.',retry:'Réessayer',stale:'Actualisation impossible. Le dernier état confirmé reste affiché.',denied:'Ces jeux ne sont plus disponibles.',saveError:'Échec de l’action. Veuillez réessayer.',empty:'Aucun jeu en cours',emptyHint:'Défiez un membre de la famille.',invitation:'Invitation',waitingReply:'Réponse attendue',turn:'À vous de jouer',waiting:'En attente de l’autre joueur',setup:'Placer la flotte',waitingFleet:'En attente de la flotte adverse',active:'Jeu en cours',finished:'Terminé récemment',round:'Manche',open:'en cours',rps:'Pierre · Papier · Ciseaux',battleship:'Bataille navale',quiz:'Quiz duel',connectFour:'Puissance 4'},
 nl:{title:'Spellen',all:'Alle',loading:'Spellen laden…',error:'Spellen konden niet worden geladen.',retry:'Opnieuw proberen',stale:'Vernieuwen mislukt. De laatst bevestigde stand blijft zichtbaar.',denied:'Deze spellen zijn niet meer beschikbaar.',saveError:'Actie mislukt. Probeer opnieuw.',empty:'Geen open spellen',emptyHint:'Daag een gezinslid uit.',invitation:'Uitnodiging',waitingReply:'Wacht op antwoord',turn:'Jij bent aan de beurt',waiting:'Wacht op de andere speler',setup:'Vloot plaatsen',waitingFleet:'Wacht op de vijandelijke vloot',active:'Spel bezig',finished:'Onlangs afgelopen',round:'Ronde',open:'open',rps:'Steen · Papier · Schaar',battleship:'Zeeslag',quiz:'Quizduel',connectFour:'Vier op een rij'},
 th:{title:'เกม',all:'ทั้งหมด',loading:'กำลังโหลดเกม…',error:'โหลดเกมไม่ได้',retry:'ลองอีกครั้ง',stale:'อัปเดตไม่ได้ ยังคงแสดงสถานะที่ยืนยันล่าสุด',denied:'เกมเหล่านี้ไม่พร้อมใช้งานแล้ว',saveError:'ดำเนินการไม่สำเร็จ โปรดลองอีกครั้ง',empty:'ไม่มีเกมที่เปิดอยู่',emptyHint:'ท้าเล่นกับสมาชิกในครอบครัว',invitation:'คำเชิญ',waitingReply:'รอคำตอบ',turn:'ตาคุณแล้ว',waiting:'รอผู้เล่นอีกคน',setup:'วางกองเรือ',waitingFleet:'รอกองเรือฝ่ายตรงข้าม',active:'เกมกำลังดำเนินอยู่',finished:'จบล่าสุด',round:'รอบ',open:'เปิดอยู่',rps:'ค้อน · กระดาษ · กรรไกร',battleship:'เรือรบ',quiz:'เกมตอบคำถาม',connectFour:'สี่เรียง'}
};
export const gamesLiveCopy=language=>text[String(language).split('-')[0]]||text.de;

// Games consumers share one bounded read per mounted family, not a global polling core.
export function useGamesLive(familyId,read){
 const readRef=useRef(read);readRef.current=read;
 const lease=useRef(null),[view,setView]=useState({familyId:null,data:null,loading:true,error:null,busy:false});
 if(lease.current?.familyId!==familyId){if(lease.current){lease.current.active=false;clearTimeout(lease.current.timer)}lease.current={familyId,active:true,data:null,initialized:false,readRevision:0,operation:0,inFlight:null,timer:null,queued:false,mutating:false,blocked:false}}
 const ctx=lease.current;
 const current=context=>context.active&&lease.current===context;
 const publish=context=>{if(current(context))setView({familyId:context.familyId,data:context.data,loading:!context.data&&!context.error,error:context.error||null,busy:context.mutating})};
 function stop(context){clearTimeout(context.timer);context.timer=null}
 function deny(context){stop(context);context.readRevision+=1;context.operation+=1;context.data=null;context.initialized=false;context.queued=false;context.blocked=true;context.mutating=false;context.error='denied';publish(context)}
 function schedule(context){stop(context);if(current(context)&&!context.mutating&&!context.blocked&&document.visibilityState!=='hidden')context.timer=setTimeout(()=>refresh(false),POLL_MS)}
 function refresh(manual=true){
  const context=lease.current;if(!current(context)||document.visibilityState==='hidden')return Promise.resolve();
  if(context.mutating){context.queued=true;return Promise.resolve()}
  if(context.inFlight){context.queued=true;return context.inFlight}
  if(context.blocked&&!manual)return Promise.resolve();if(manual)context.blocked=false;
  stop(context);const revision=context.readRevision;context.error=null;publish(context);
  const request=(async()=>{try{const value=await readRef.current({initial:!context.initialized});if(!current(context)||revision!==context.readRevision)return;context.data={...(context.data||{}),...value};context.initialized=true;context.error=null;publish(context)}catch(error){if(!current(context)||revision!==context.readRevision)return;if(denied(error))deny(context);else{context.error=context.data?'stale':'error';publish(context)}}finally{if(!current(context))return;context.inFlight=null;if(context.queued&&!context.mutating&&!context.blocked&&document.visibilityState!=='hidden'){context.queued=false;refresh(false)}else schedule(context)}})();
  context.inFlight=request;return request;
 }
 function beginMutation(){const context=lease.current;if(!current(context)||context.mutating||context.blocked)return null;stop(context);context.readRevision+=1;context.operation+=1;context.mutating=true;context.error=null;context.queued=false;publish(context);const operation=context.operation;return {context,current:()=>current(context)&&operation===context.operation}}
 function update(transform,token){const context=token?.context||lease.current;if(!current(context)||(token&&!token.current()))return;context.data=transform(context.data||{});publish(context)}
 function failMutation(error,token){if(!token?.current())return;if(denied(error))deny(token.context);else{token.context.error='saveError';publish(token.context)}}
 function finishMutation(token){if(!token?.current())return;token.context.mutating=false;publish(token.context);if(token.context.inFlight)token.context.queued=true;else schedule(token.context)}
 useEffect(()=>{
  const context=lease.current;context.active=true;refresh(false);
  const visibility=()=>{stop(context);if(document.visibilityState==='hidden')context.queued=false;else refresh(true)};
  const focus=()=>{if(document.visibilityState!=='hidden')refresh(true)};
  const auth=event=>{if(event.detail?.authenticated===false){context.active=false;stop(context);context.data=null;context.readRevision+=1;context.operation+=1;setView({familyId:context.familyId,data:null,loading:false,error:'denied',busy:false})}};
  document.addEventListener('visibilitychange',visibility);window.addEventListener('focus',focus);window.addEventListener(AUTH_CHANGED_EVENT,auth);
  return()=>{context.active=false;stop(context);document.removeEventListener('visibilitychange',visibility);window.removeEventListener('focus',focus);window.removeEventListener(AUTH_CHANGED_EVENT,auth)};
 },[familyId]);
 return {...(view.familyId===familyId?view:{data:null,loading:true,error:null,busy:false}),refresh,beginMutation,update,failMutation,finishMutation};
}

function opponent(match){return match.am_challenger?match.opponent:match.challenger}
function rpsNeedsMove(match){if(match.game_type!=='rps'||match.status!=='active')return false;const current=match.rps?.rounds?.find(row=>row.number===match.rps?.current_round);return !current?.submitted_by_me}
function quizNeedsMove(match){return match.game_type==='quiz'&&match.status==='active'&&Boolean(match.quiz?.needs_answer)}
function needsSetup(match){return match.game_type==='battleship'&&match.status==='active'&&match.battleship?.phase==='setup'&&!match.battleship?.my_fleet_confirmed}
function isActionable(match){return Boolean(match.can_accept||match.is_my_turn||rpsNeedsMove(match)||quizNeedsMove(match)||needsSetup(match))}
function gameName(match,s){return match.game_type==='rps'?s.rps:match.game_type==='battleship'?s.battleship:match.game_type==='quiz'?s.quiz:s.connectFour}
function gameIcon(match){return match.game_type==='quiz'?'check':match.game_type==='connect_four'?'members':match.game_type==='rps'?'check':'members'}
function label(match,s){if(match.can_accept)return s.invitation;if(match.status==='pending')return s.waitingReply;if(match.game_type==='rps'&&match.status==='active')return `${s.round} ${match.rps?.current_round||1} / ${match.rps?.round_count||1} · ${rpsNeedsMove(match)?s.turn:s.waiting}`;if(match.game_type==='quiz'&&match.status==='active')return `${s.round} ${match.quiz?.current_round||1} / ${match.quiz?.round_count||1} · ${quizNeedsMove(match)?s.turn:s.waiting}`;if(match.game_type==='battleship'&&match.status==='active'&&match.battleship?.phase==='setup')return match.battleship?.my_fleet_confirmed?s.waitingFleet:s.setup;if(match.is_my_turn)return s.turn;if(match.status==='active')return s.waiting;if(match.status==='finished')return s.finished;return s.active}
function rank(match){if(match.can_accept)return 0;if(isActionable(match))return 1;if(match.status==='active'||match.status==='pending')return 2;return 3}

export default function GamesTodayWidget({family,language='de'}){
 const s=gamesLiveCopy(language),live=useGamesLive(family.id,async()=>({summary:await api(`/games/summary/?family=${encodeURIComponent(family.id)}`)})),data=live.data?.summary;
 const candidates=[...(data?.actionable||[]),...(data?.recent||[])];const rows=[...new Map(candidates.map(row=>[row.id,row])).values()].sort((a,b)=>rank(a)-rank(b)).slice(0,3);const actionableCount=(data?.actionable||[]).filter(row=>row.status!=='finished').length;
 const open=match=>{const suffix=match?`&game=${encodeURIComponent(match.id)}`:'';window.location.assign(`/?page=games${suffix}`)};
 return <section className="today-section today-games" data-testid="today-games"><div className="today-section-head"><div><h2>{s.title}</h2><small>{actionableCount?`${actionableCount} ${s.open}`:(rows.length||0)}</small></div><button type="button" className="today-link" onClick={()=>open()}>{s.all} <Icon name="next"/></button></div>{live.error&&<div className="today-calm" role="alert"><Icon name="warning"/><strong>{s[live.error]||s.error}</strong><button type="button" className="text-button" onClick={()=>live.refresh()}>{s.retry}</button></div>}{!data&&!live.error?<div className="today-calm" role="status"><Icon name="refresh"/><span>{s.loading}</span></div>:data&&rows.length?<div className="today-inbox-list">{rows.map(match=><button type="button" key={match.id} onClick={()=>open(match)} aria-label={`${gameName(match,s)} · ${opponent(match)?.display_name||''} · ${label(match,s)}`}><span className={`today-inbox-icon ${isActionable(match)?'unread':''}`}><Icon name={gameIcon(match)}/></span><span className="grow"><strong>{gameName(match,s)}</strong><small>{[opponent(match)?.display_name,label(match,s)].filter(Boolean).join(' · ')}</small></span>{isActionable(match)&&<i aria-hidden="true"/>}<Icon name="next"/></button>)}</div>:data?<button type="button" className="today-calm" onClick={()=>open()}><Icon name="members"/><strong>{s.empty}</strong><span>{s.emptyHint}</span></button>:null}</section>
}
