import {useEffect,useMemo,useState} from 'react';
import {api} from './api';

const CONTENT_ROLES=new Set(['owner','adult','teen','child','guest']);
const MESSAGE_ROLES=new Set(['owner','adult','teen']);
const SETTINGS_ROLES=new Set(['owner','adult']);

export function permissionsForRole(role){
 return {
  createContent:CONTENT_ROLES.has(role||''),
  createMessages:MESSAGE_ROLES.has(role||''),
  manageSettings:SETTINGS_ROLES.has(role||''),
 };
}

export function useFamilyPermissions(family){
 const [session,setSession]=useState(null);
 useEffect(()=>{let active=true;api('/auth/session/').then(value=>{if(active)setSession(value)}).catch(()=>{if(active)setSession(null)});return()=>{active=false}},[family?.id]);
 const membership=useMemo(()=>family?.memberships?.find(item=>String(item.user)===String(session?.user?.id))||null,[family,session?.user?.id]);
 const role=membership?.role||null;
 const permissions=useMemo(()=>permissionsForRole(role),[role]);
 return {session,membership,role,permissions,canManageSettings:permissions.manageSettings};
}
