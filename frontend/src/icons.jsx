import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
  faHouse, faListCheck, faCartShopping, faClockRotateLeft, faEllipsis, faPlus, faCalendarDays, faCloudSun, faTrashCan,
  faPlug, faInbox, faUsers, faLanguage, faRightFromBracket, faRightToBracket, faWifi, faTriangleExclamation, faCheck, faRotate,
  faArrowLeft, faChevronRight, faXmark, faWandMagicSparkles, faBolt, faSnowflake, faCloudRain, faBell,
  faMagnifyingGlass, faFilter, faPen, faTrash, faStar, faStore, faLayerGroup, faClock, faUser, faCircleInfo,
  faArrowTrendUp, faFire, faGrip, faCopy, faShareNodes, faLink, faGear, faCirclePlus, faCheckDouble, faBarsProgress,
  faLocationDot, faTags, faGaugeHigh, faRobot, faEnvelope, faArrowDownShortWide, faBus, faGraduationCap, faLightbulb,
  faDownload, faPlay, faHeart, faBoxArchive, faSliders, faRoute, faReceipt, faCamera, faUpload, faEuroSign, faLock,
  faMoneyBillTransfer
} from '@fortawesome/free-solid-svg-icons';

export const icons = {
  home:faHouse, smartHome:faHouse, tasks:faListCheck, shopping:faCartShopping, history:faClockRotateLeft, more:faEllipsis, plus:faPlus,
  calendar:faCalendarDays, weather:faCloudSun, waste:faTrashCan, integrations:faPlug, inbox:faInbox, members:faUsers,
  language:faLanguage, logout:faRightFromBracket, login:faRightToBracket, online:faWifi, offline:faTriangleExclamation, check:faCheck, refresh:faRotate,
  back:faArrowLeft, next:faChevronRight, close:faXmark, automation:faWandMagicSparkles, bolt:faBolt, frost:faSnowflake,
  rain:faCloudRain, warning:faBell, search:faMagnifyingGlass, filter:faFilter, edit:faPen, delete:faTrash, favorite:faStar,
  store:faStore, lists:faLayerGroup, clock:faClock, user:faUser, info:faCircleInfo, trend:faArrowTrendUp, hot:faFire,
  drag:faGrip, copy:faCopy, share:faShareNodes, link:faLink, settings:faGear, addCircle:faCirclePlus, doneAll:faCheckDouble,
  progress:faBarsProgress, location:faLocationDot, tags:faTags, priority:faGaugeHigh, robot:faRobot, email:faEnvelope,
  sort:faArrowDownShortWide, transit:faBus, school:faGraduationCap, light:faLightbulb, install:faDownload, play:faPlay,
  heart:faHeart, archive:faBoxArchive, sliders:faSliders, route:faRoute, receipt:faReceipt, camera:faCamera, upload:faUpload,
  euro:faEuroSign, lock:faLock, settle:faMoneyBillTransfer,
};

export function Icon({name, size=18, className='', title}){
  const icon=icons[name]||icons.info;
  return <FontAwesomeIcon icon={icon} className={className} title={title} style={{fontSize:size}}/>;
}
