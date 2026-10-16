import {createPortal} from 'react-dom';

/**
 * Render app overlays at the document root so page scroll containers and
 * stacking contexts can never compete with modal/dialog layers.
 */
export default function OverlayPortal({children,container}){
  if(typeof document==='undefined')return null;
  return createPortal(children,container||document.body);
}
