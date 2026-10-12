import {useEffect,useState} from 'react';
import {api} from './api';
import {Icon} from './icons';

const text={
 de:{title:'Spiele',all:'Alle',loading:'Spiele werden geladen …',error:'Spiele konnten nicht geladen werden.',retry:'Erneut laden',empty:'Keine offenen Spiele',emptyHint:'Fordere ein Familienmitglied heraus.',challenge:'Herausforderung',turn:'Du bist am Zug',setup:'Flotte setzen',active:'Spiel läuft',finished:'Zuletzt beendet',rps:'Schere · Stein · Papier',battleship:'Schiffe versenken'},
 en:{title:'Games',all:'All',loading:'Loading games …',error:'Games could not be loaded.',retry:'Retry',empty:'No open games',emptyHint:'Challenge a family member.',challenge:'Challenge',turn:'Your turn',setup:'Place fleet',active:'Game in progress',finished:'Recently finished',rps:'Rock · Paper · Scissors',battleship:'Battleship'}
};

function opponent(match){return match.am_challenger?match.opponent:match.challenger}
function rpsNeedsMove(match){if(match.game_type!=='rps'||match.status!=='active')return false;const current=match.rps?.rounds?.find(row=>row.number===match.rps?.current_round);return !current?.submitted_by_me}
function label(match,s){if(match.can_accept)return s.challenge;if(match.is_my_turn||rpsNeedsMove(match))return s.turn;if(match.battleship?.phase==='setup'&&!match.battleship?.my_fleet_confirmed)return s.setup;if(match.status==='finished')return s.finished;return s.active}

export default function GamesTodayWidget({family,language='de'}){
 const s=text[String(language).startsWith('en')?'en':'de'];const [data,setData]=useState(null);const [error,setError]=useState(false);
 const load=()=>{setError(false);api(`/games/summary/?family=${encodeURIComponent(family.id)}`).then(setData).catch(()=>setError(true))};
 useEffect(()=>{let active=true;setData(null);setError(false);api(`/games/summary/?family=${encodeURIComponent(family.id)}`).then(value=>{if(active)setData(value)}).catch(()=>{if(active)setError(true)});return()=>{active=false}},[family.id]);
 const candidates=[...(data?.actionable||[]),...(data?.recent||[]).filter(row=>row.status!=='finished')];const rows=[...new Map(candidates.map(row=>[row.id,row])).values()].sort((a,b)=>Number(Boolean(label(b,s)===s.turn||label(b,s)===s.challenge||label(b,s)===s.setup))-Number(Boolean(label(a,s)===s.turn||label(a,s)===s.challenge||label(a,s)===s.setup))).slice(0,3);
 const open=match=>{const suffix=match?`&game=${encodeURIComponent(match.id)}`:'';window.location.assign(`/?page=games${suffix}`)};
 return <section className="today-section today-games" data-testid="today-games"><div className="today-section-head"><div><h2>{s.title}</h2><small>{rows.length||0}</small></div><button className="today-link" onClick={()=>open()}>{s.all} <Icon name="next"/></button></div>{error?<div className="today-calm" role="alert"><Icon name="warning"/><strong>{s.error}</strong><button className="text-button" onClick={load}>{s.retry}</button></div>:!data?<div className="today-calm" role="status"><Icon name="refresh"/><span>{s.loading}</span></div>:rows.length?<div className="today-inbox-list">{rows.map(match=><button key={match.id} onClick={()=>open(match)}><span className="today-inbox-icon"><Icon name={match.game_type==='rps'?'check':'members'}/></span><span className="grow"><strong>{match.game_type==='rps'?s.rps:s.battleship}</strong><small>{opponent(match)?.display_name} · {label(match,s)}</small></span><Icon name="next"/></button>)}</div>:<button className="today-calm" onClick={()=>open()}><Icon name="members"/><strong>{s.empty}</strong><span>{s.emptyHint}</span></button>}</section>
}
