import {useEffect,useState} from 'react';
import QRCode from 'qrcode';

export default function InviteQr({value,label='Einladungslink als QR-Code'}){
 const [src,setSrc]=useState('');
 const [error,setError]=useState(false);
 useEffect(()=>{
  let active=true;
  setSrc('');setError(false);
  if(!value)return()=>{active=false};
  QRCode.toDataURL(value,{width:240,margin:2,errorCorrectionLevel:'M'})
   .then(url=>{if(active)setSrc(url)})
   .catch(()=>{if(active)setError(true)});
  return()=>{active=false};
 },[value]);
 if(error)return <span className="invite-qr-error">QR-Code konnte nicht erzeugt werden.</span>;
 if(!src)return <span className="invite-qr-loading">QR-Code wird erzeugt…</span>;
 return <img className="invite-qr-image" src={src} alt={label}/>;
}
