import {useInsertionEffect,useRef} from 'react';

// Release legacy inert attributes before Base UI's layout effects take ownership.
export default function useOverlayOwnership() {
  const fallback=useRef(null);
  useInsertionEffect(() => {
    const detail={returnFocus:null};
    document.dispatchEvent(new CustomEvent('familyos:managed-overlay-mount',{detail}));
    fallback.current=detail.returnFocus;
  }, []);
  return preferred=>{
    if(preferred?.isConnected&&preferred!==document.body)return preferred;
    return fallback.current?.isConnected?fallback.current:true;
  };
}
