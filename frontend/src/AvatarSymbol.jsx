import {FontAwesomeIcon} from '@fortawesome/react-fontawesome';
import {
 faCakeCandles,faCat,faDragon,faFish,faFootball,faGamepad,faGift,faMoon,
 faMusic,faRainbow,faRocket,faSun,faTree
} from '@fortawesome/free-solid-svg-icons';
import {Icon} from './icons';

const EXTRA={
 cake:faCakeCandles,
 cat:faCat,
 dragon:faDragon,
 fish:faFish,
 football:faFootball,
 gamepad:faGamepad,
 gift:faGift,
 moon:faMoon,
 music:faMusic,
 rainbow:faRainbow,
 rocket:faRocket,
 sun:faSun,
 tree:faTree,
};

export const EXTRA_AVATAR_SYMBOLS=Object.freeze(Object.keys(EXTRA));

export default function AvatarSymbol({name,size=18,className='',title}){
 const glyph=EXTRA[name];
 if(!glyph)return <Icon name={name} size={size} className={className} title={title}/>;
 return <FontAwesomeIcon icon={glyph} style={{fontSize:size}} className={className} title={title||undefined}/>;
}
