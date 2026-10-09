import {useEffect,useMemo,useState} from 'react';
import {api} from './api';

export function useFamilyPermissions(family){
 const [session,setSession]=useState(null);
 useEffect(()=>{let active=true;api('/auth/session/').then(value=>{if(active)setSession(value)}).catch(()=>{if(active)setSession(null)});return()=>{active=false}},[family?.id]);
 const membership=useMemo(()=>family?.memberships?.find(item=>String(item.user)===String(session?.user?.id))||null,[family,session?.user?.id]);
 const role=membership?.role||null;
 return {session,membership,role,canManageSettings:role==='owner'||role==='adult'};
}
