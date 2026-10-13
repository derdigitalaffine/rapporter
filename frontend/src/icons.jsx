import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faBed, faDog, faBowlFood, faDroplet, faBroom, faUtensils, faCar, faRecycle, faHouse, faListCheck, faCartShopping, faClockRotateLeft, faEllipsis, faPlus, faCalendarDays, faCloudSun, faTrashCan,
  faPlug, faInbox, faUsers, faLanguage, faRightFromBracket, faRightToBracket, faWifi, faTriangleExclamation, faCheck, faRotate,
  faArrowLeft, faChevronRight, faXmark, faWandMagicSparkles, faBolt, faSnowflake, faCloudRain, faBell,
  faMagnifyingGlass, faFilter, faPen, faTrash, faStar, faStore, faLayerGroup, faClock, faUser, faCircleInfo,
  faArrowTrendUp, faFire, faGrip, faCopy, faShareNodes, faLink, faGear, faCirclePlus, faCheckDouble, faBarsProgress,
  faLocationDot, faTags, faGaugeHigh, faRobot, faEnvelope, faArrowDownShortWide, faBus, faGraduationCap, faLightbulb,
  faDownload, faPlay, faHeart, faBoxArchive, faSliders, faRoute, faReceipt, faCamera, faUpload, faEuroSign, faLock,
  faMoneyBillTransfer, faBaby, faPaw, faMicrophone, faStop, faPaperPlane
} from '@fortawesome/free-solid-svg-icons';

// Utility and low-frequency symbols stay on Font Awesome for compatibility. The
// high-visibility FamilyOS navigation/module layer below uses one calmer,
// rounded 24×24 outline language while inheriting every existing CSS color.
export const icons = {
  bed:faBed, dog:faDog, 'bowl-food':faBowlFood, water:faDroplet, broom:faBroom, utensils:faUtensils, car:faCar, recycle:faRecycle,
  home:faHouse, smartHome:faHouse, tasks:faListCheck, shopping:faCartShopping, history:faClockRotateLeft, more:faEllipsis, plus:faPlus,
  calendar:faCalendarDays, weather:faCloudSun, waste:faTrashCan, integrations:faPlug, inbox:faInbox, members:faUsers, users:faUsers,
  language:faLanguage, logout:faRightFromBracket, login:faRightToBracket, online:faWifi, offline:faTriangleExclamation, check:faCheck, refresh:faRotate,
  back:faArrowLeft, next:faChevronRight, chevronRight:faChevronRight, close:faXmark, automation:faWandMagicSparkles, bolt:faBolt, frost:faSnowflake,
  rain:faCloudRain, warning:faBell, search:faMagnifyingGlass, filter:faFilter, edit:faPen, delete:faTrash, favorite:faStar,
  store:faStore, lists:faLayerGroup, clock:faClock, user:faUser, info:faCircleInfo, trend:faArrowTrendUp, hot:faFire,
  drag:faGrip, copy:faCopy, share:faShareNodes, link:faLink, settings:faGear, addCircle:faCirclePlus, doneAll:faCheckDouble,
  progress:faBarsProgress, location:faLocationDot, tags:faTags, priority:faGaugeHigh, robot:faRobot, email:faEnvelope,
  sort:faArrowDownShortWide, transit:faBus, school:faGraduationCap, light:faLightbulb, install:faDownload, play:faPlay,
  heart:faHeart, archive:faBoxArchive, sliders:faSliders, route:faRoute, receipt:faReceipt, camera:faCamera, upload:faUpload,
  microphone:faMicrophone, stop:faStop, send:faPaperPlane,
  euro:faEuroSign, lock:faLock, key:faLock, settle:faMoneyBillTransfer, baby:faBaby, pet:faPaw,
};

const outlineGlyphs = {
  home: () => <>
    <path d="M3.8 10.7 12 4l8.2 6.7"/>
    <path d="M5.8 9.5v8.8a1.7 1.7 0 0 0 1.7 1.7h9a1.7 1.7 0 0 0 1.7-1.7V9.5"/>
    <path d="M9.2 20v-6.2h5.6V20"/>
  </>,
  tasks: () => <>
    <rect x="4" y="3.5" width="16" height="17" rx="3"/>
    <path d="m7.4 8.2 1.3 1.3 2.2-2.4M13.5 8.5h3.2M7.4 14.2l1.3 1.3 2.2-2.4M13.5 14.5h3.2"/>
  </>,
  shopping: () => <>
    <path d="M3.8 5.5h2l1.7 9.1a2 2 0 0 0 2 1.6h7.1a2 2 0 0 0 1.9-1.5l1.1-5.2H7"/>
    <circle cx="10" cy="19.3" r="1.1"/><circle cx="17" cy="19.3" r="1.1"/>
  </>,
  calendar: () => <>
    <rect x="3.8" y="5.1" width="16.4" height="15" rx="3"/>
    <path d="M7.8 3.5v3.2M16.2 3.5v3.2M3.8 9h16.4"/>
    <path d="M8 12.5h.01M12 12.5h.01M16 12.5h.01M8 16.2h.01M12 16.2h.01" strokeWidth="2.5"/>
  </>,
  more: () => <>
    <circle cx="5.2" cy="12" r="1.25"/><circle cx="12" cy="12" r="1.25"/><circle cx="18.8" cy="12" r="1.25"/>
  </>,
  history: () => <>
    <path d="M4.6 8.1V4.7M4.6 4.7H8"/>
    <path d="M5 5.3a8.2 8.2 0 1 1-1.2 9.9"/>
    <path d="M12 7.7V12l3 1.8"/>
  </>,
  weather: () => <>
    <path d="M15.8 7.2a4.1 4.1 0 0 0-7.6 2.2 3.5 3.5 0 0 0 .4 7h7.7a4.1 4.1 0 0 0-.5-8.2Z"/>
    <path d="M17.7 4.1v-1M20.5 5.3l.8-.8M21.7 8.2h1M14.9 4.7l-.7-.8"/>
  </>,
  inbox: () => <>
    <path d="M4.5 6.2h15l1.2 8.2v3.1a2 2 0 0 1-2 2H5.3a2 2 0 0 1-2-2v-3.1z"/>
    <path d="M3.5 14.2h4.2l1.4 2h5.8l1.4-2h4.2"/>
  </>,
  members: () => <>
    <circle cx="9" cy="8.2" r="3"/>
    <path d="M3.8 19.4c.4-3.5 2.2-5.5 5.2-5.5s4.8 2 5.2 5.5"/>
    <circle cx="16.7" cy="9.2" r="2.2"/>
    <path d="M15.3 14.5c.5-.3 1-.4 1.6-.4 2.3 0 3.7 1.7 4 4.5"/>
  </>,
  user: () => <>
    <circle cx="12" cy="8" r="3.4"/>
    <path d="M5.5 20c.5-4.2 2.7-6.5 6.5-6.5s6 2.3 6.5 6.5"/>
  </>,
  route: () => <>
    <circle cx="6" cy="5.5" r="2.2"/><circle cx="18" cy="18.5" r="2.2"/>
    <path d="M7.8 6.8c2.5 1.5 7.7.7 7.8 3.9.1 2.9-5.8 1.6-6 4.6-.1 1.5 1.4 2.4 3 2.7"/>
  </>,
  check: () => <path d="m5.2 12.4 4.2 4.1 9.4-9.2"/>,
  heart: () => <path d="M12 20.1S4.2 15.7 4.2 9.5A4.2 4.2 0 0 1 12 7.3a4.2 4.2 0 0 1 7.8 2.2c0 6.2-7.8 10.6-7.8 10.6Z"/>,
  receipt: () => <>
    <path d="M6 3.8h12v16.4l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3-2 1.3z"/>
    <path d="M9 8h6M9 11.8h6M9 15.6h4"/>
  </>,
  store: () => <>
    <path d="M4.3 9.2 6 4.5h12l1.7 4.7"/>
    <path d="M4.3 9.2c0 1.5 1 2.7 2.4 2.7 1.2 0 2.1-.8 2.4-1.9.3 1.1 1.4 1.9 2.9 1.9s2.6-.8 2.9-1.9c.3 1.1 1.2 1.9 2.4 1.9 1.4 0 2.4-1.2 2.4-2.7"/>
    <path d="M5.8 11.6v8h12.4v-8M9.1 19.6v-4.8h5.8v4.8"/>
  </>,
  warning: () => <>
    <path d="M18.2 9.5c0-3.5-2.3-5.9-6.2-5.9S5.8 6 5.8 9.5c0 5.1-2 6.2-2 6.2h16.4s-2-1.1-2-6.2Z"/>
    <path d="M9.5 19.1c.7.9 1.5 1.3 2.5 1.3s1.8-.4 2.5-1.3"/>
  </>,
  integrations: () => <>
    <path d="M8.2 4.2v4M5.4 6.2H11M15.8 15.8v4M13 17.8h5.6"/>
    <path d="M8.2 8.2v2.1a5.5 5.5 0 0 0 5.5 5.5h2.1"/>
  </>,
  automation: () => <>
    <path d="m12 3.8.7 2.1a4.5 4.5 0 0 0 2.8 2.8l2.1.7-2.1.7a4.5 4.5 0 0 0-2.8 2.8L12 15l-.7-2.1a4.5 4.5 0 0 0-2.8-2.8l-2.1-.7 2.1-.7a4.5 4.5 0 0 0 2.8-2.8z"/>
    <path d="m18.1 15.1.35 1.05a2.5 2.5 0 0 0 1.55 1.55l1.05.35-1.05.35a2.5 2.5 0 0 0-1.55 1.55L18.1 21l-.35-1.05a2.5 2.5 0 0 0-1.55-1.55l-1.05-.35 1.05-.35a2.5 2.5 0 0 0 1.55-1.55z"/>
  </>,
  baby: () => <>
    <path d="M12.2 5.2c1.1-1.7 2.7-2.4 4.1-1.8-.2 1.8-1.3 3-3.4 3.4"/>
    <circle cx="12" cy="11" r="5.2"/>
    <path d="M9.6 10.5h.01M14.4 10.5h.01M10.2 13.1c.6.7 1.2 1 1.8 1s1.2-.3 1.8-1" strokeWidth="2.3"/>
    <path d="M7.5 19.8c1.2-1.7 2.7-2.6 4.5-2.6s3.3.9 4.5 2.6"/>
  </>,
  pet: () => <>
    <ellipse cx="12" cy="14.9" rx="4.1" ry="3.6"/>
    <ellipse cx="6.8" cy="10.1" rx="1.8" ry="2.3" transform="rotate(-28 6.8 10.1)"/>
    <ellipse cx="17.2" cy="10.1" rx="1.8" ry="2.3" transform="rotate(28 17.2 10.1)"/>
    <ellipse cx="9.3" cy="6.5" rx="1.6" ry="2.1" transform="rotate(-10 9.3 6.5)"/>
    <ellipse cx="14.7" cy="6.5" rx="1.6" ry="2.1" transform="rotate(10 14.7 6.5)"/>
  </>,
};

const outlineAliases = {smartHome:'home', users:'members'};

function OutlineIcon({name,size,className,title}){
  const resolved=outlineAliases[name]||name;
  const Glyph=outlineGlyphs[resolved];
  if(!Glyph)return null;
  return <svg
    viewBox="0 0 24 24"
    width="1em"
    height="1em"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.85"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={`familyos-icon ${className}`.trim()}
    style={{fontSize:size}}
    role={title?'img':undefined}
    aria-label={title||undefined}
    aria-hidden={title?undefined:true}
    focusable="false"
  >
    {title&&<title>{title}</title>}
    <Glyph/>
  </svg>;
}

export function Icon({name, size=18, className='', title}){
  const resolved=outlineAliases[name]||name;
  if(outlineGlyphs[resolved])return <OutlineIcon name={name} size={size} className={className} title={title}/>;
  const icon=icons[name]||icons.info;
  return <FontAwesomeIcon icon={icon} className={className} title={title} style={{fontSize:size}}/>;
}
