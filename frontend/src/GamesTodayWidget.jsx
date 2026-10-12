import {useCallback,useEffect,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';

const POLL_MS=4000;
const text={
 de:{title:'Spiele',all:'Alle',loading:'Spiele werden geladen …',error:'Spiele konnten nicht geladen werden.',retry:'Erneut laden',empty:'Keine offenen Spiele',emptyHint:'Fordere ein Familienmitglied heraus.',invitation:'Einladung',waitingReply:'Antwort ausstehend',turn:'Du bist am Zug',waiting:'Wartet auf die andere Person',setup:'Flotte setzen',waitingFleet:'Wartet auf die gegnerische Flotte',active:'Spiel läuft',finished:'Zuletzt beendet',round:'Runde',open:'offen',rps:'Schere · Stein · Papier',battleship:'Schiffe versenken'},
 en:{title:'Games',all:'All',loading:'Loading games …',error:'Games could not be loaded.',retry:'Retry',empty:'No open games',emptyHint:'Challenge a family member.',invitation:'Invitation',waitingReply:'Waiting for reply',turn:'Your turn',waiting:'Waiting for the other player',setup:'Place fleet',waitingFleet:'Waiting for opponent fleet',active:'Game in progress',finished:'Recently finished',round:'Round',open:'open',rps:'Rock · Paper · Scissors',battleship:'Battleship'}
};

function opponent(match){return match.am_challenger?match.opponent:match.challenger}
function rpsNeedsMove(match){if(match.game_type!=='rps'||match.status!=='active')return false;const current=match.rps?.rounds?.find(row=>row.number===match.rps?.current_round);return !current?.submitted_by_me}
function needsSetup(match){return match.game_type==='battleship'&&match.status==='active'&&match.battleship?.phase==='setup'&&!match.battleship?.my_fleet_confirmed}
function isActionable(match){return Boolean(match.can_accept||match.is_my_turn||rpsNeedsMove(match)||needsSetup(match))}
function label(match,s){
 if(match.can_accept)return s.invitation;
 if(match.status==='pending')return s.waitingReply;
 if(match.game_type==='rps'&&match.status==='active')return `${s.round} ${match.rps?.current_round||1} / ${match.rps?.round_count||1} · ${rpsNeedsMove(match)?s.turn:s.waiting}`;
 if(match.game_type==='battleship'&&match.status==='active'&&match.battleship?.phase==='setup')return match.battleship?.my_fleet_confirmed?s.waitingFleet:s.setup;
 if(match.is_my_turn)return s.turn;
 if(match.status==='active')return s.waiting;
 if(match.status==='finished')return s.finished;
 return s.active;
}
function rank(match){if(match.can_accept)return 0;if(isActionable(match))return 1;if(match.status==='active'||match.status==='pending')return 2;return 3}

export default function GamesTodayWidget({family,language='de'}){
 const s=text[String(language).startsWith('en')?'en':'de'];const [data,setData]=useState(null);const [error,setError]=useState(false);
 const load=useCallback(async({initial=false}={})=>{if(initial)setData(null);setError(false);try{setData(await api(`/games/summary/?family=${encodeURIComponent(family.id)}`))}catch{setError(true)}},[family.id]);
 useEffect(()=>{
  let cancelled=false;let timer=null;
  const refresh=async()=>{if(cancelled||document.visibilityState==='hidden')return;try{const value=await api(`/games/summary/?family=${encodeURIComponent(family.id)}`);if(!cancelled){setData(value);setError(false)}}catch{if(!cancelled&&data===null)setError(true)}};
  const start=()=>{if(timer){clearInterval(timer);timer=null}if(document.visibilityState==='visible'){refresh();timer=setInterval(refresh,POLL_MS)}};
  start();
  const onVisibility=()=>start();const onFocus=()=>{if(document.visibilityState!=='hidden')refresh()};
  document.addEventListener('visibilitychange',onVisibility);window.addEventListener('focus',onFocus);
  return()=>{cancelled=true;if(timer)clearInterval(timer);document.removeEventListener('visibilitychange',onVisibility);window.removeEventListener('focus',onFocus)};
 },[family.id]);
 const candidates=[...(data?.actionable||[]),...(data?.recent||[])];const rows=[...new Map(candidates.map(row=>[row.id,row])).values()].sort((a,b)=>rank(a)-rank(b)).slice(0,3);const actionableCount=(data?.actionable||[]).filter(row=>row.status!=='finished').length;
 const open=match=>{const suffix=match?`&game=${encodeURIComponent(match.id)}`:'';window.location.assign(`/?page=games${suffix}`)};
 return <section className="today-section today-games" data-testid="today-games"><div className="today-section-head"><div><h2>{s.title}</h2><small>{actionableCount?`${actionableCount} ${s.open}`:(rows.length||0)}</small></div><button className="today-link" onClick={()=>open()}>{s.all} <Icon name="next"/></button></div>{error&&!data?<div className="today-calm" role="alert"><Icon name="warning"/><strong>{s.error}</strong><button className="text-button" onClick={()=>load({initial:true})}>{s.retry}</button></div>:!data?<div className="today-calm" role="status"><Icon name="refresh"/><span>{s.loading}</span></div>:rows.length?<div className="today-inbox-list">{rows.map(match=><button key={match.id} onClick={()=>open(match)} aria-label={`${match.game_type==='rps'?s.rps:s.battleship} · ${opponent(match)?.display_name||''} · ${label(match,s)}`}><span className={`today-inbox-icon ${isActionable(match)?'unread':''}`}><Icon name={match.game_type==='rps'?'check':'members'}/></span><span className="grow"><strong>{match.game_type==='rps'?s.rps:s.battleship}</strong><small>{[opponent(match)?.display_name,label(match,s)].filter(Boolean).join(' · ')}</small></span>{isActionable(match)&&<i aria-hidden="true"/>}<Icon name="next"/></button>)}</div>:<button className="today-calm" onClick={()=>open()}><Icon name="members"/><strong>{s.empty}</strong><span>{s.emptyHint}</span></button>}</section>
}