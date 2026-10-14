import {adminApi} from './superadmin-api';

export const superadminWebAuthnAvailable=()=>typeof window!=='undefined'&&Boolean(window.PublicKeyCredential)&&Boolean(navigator.credentials?.create)&&Boolean(navigator.credentials?.get);

function decodeBase64Url(value){
 const normalized=String(value||'').replace(/-/g,'+').replace(/_/g,'/');
 const padded=normalized+'='.repeat((4-normalized.length%4)%4);
 const binary=atob(padded);
 return Uint8Array.from(binary,char=>char.charCodeAt(0));
}

function encodeBase64Url(value){
 if(value===null||value===undefined)return null;
 const bytes=value instanceof ArrayBuffer?new Uint8Array(value):new Uint8Array(value.buffer,value.byteOffset,value.byteLength);
 let binary='';
 for(const byte of bytes)binary+=String.fromCharCode(byte);
 return btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}

function registrationOptions(options={}){
 return {
  ...options,
  challenge:decodeBase64Url(options.challenge),
  user:{...options.user,id:decodeBase64Url(options.user?.id)},
  excludeCredentials:(options.excludeCredentials||[]).map(item=>({...item,id:decodeBase64Url(item.id)})),
 };
}

function authenticationOptions(options={}){
 return {
  ...options,
  challenge:decodeBase64Url(options.challenge),
  allowCredentials:(options.allowCredentials||[]).map(item=>({...item,id:decodeBase64Url(item.id)})),
 };
}

function registrationCredential(credential){
 const response=credential.response;
 return {
  id:credential.id,
  rawId:encodeBase64Url(credential.rawId),
  type:credential.type,
  authenticatorAttachment:credential.authenticatorAttachment||undefined,
  clientExtensionResults:credential.getClientExtensionResults?.()||{},
  response:{
   clientDataJSON:encodeBase64Url(response.clientDataJSON),
   attestationObject:encodeBase64Url(response.attestationObject),
   transports:response.getTransports?.()||[],
  },
 };
}

function authenticationCredential(credential){
 const response=credential.response;
 return {
  id:credential.id,
  rawId:encodeBase64Url(credential.rawId),
  type:credential.type,
  authenticatorAttachment:credential.authenticatorAttachment||undefined,
  clientExtensionResults:credential.getClientExtensionResults?.()||{},
  response:{
   clientDataJSON:encodeBase64Url(response.clientDataJSON),
   authenticatorData:encodeBase64Url(response.authenticatorData),
   signature:encodeBase64Url(response.signature),
   userHandle:encodeBase64Url(response.userHandle),
  },
 };
}

export function superadminPasskeyError(error){
 if(error?.name==='NotAllowedError')return 'Der Passkey-Vorgang wurde abgebrochen oder ist abgelaufen.';
 if(error?.name==='InvalidStateError')return 'Dieser Passkey ist bereits für die Superadmin-App registriert.';
 if(error?.name==='SecurityError')return 'Passkeys sind für diese Origin nicht verfügbar.';
 return error?.message||'Passkey-Vorgang fehlgeschlagen.';
}

export async function createSuperadminPasskey(name){
 if(!superadminWebAuthnAvailable())throw new Error('Dieser Browser unterstützt die benötigte Passkey-Funktion nicht.');
 const start=await adminApi('/auth/passkeys/register/options/',{method:'POST',body:'{}'});
 const credential=await navigator.credentials.create({publicKey:registrationOptions(start.options)});
 if(!credential)throw new Error('Es wurde kein Passkey erstellt.');
 return adminApi('/auth/passkeys/register/verify/',{
  method:'POST',
  body:JSON.stringify({challenge_id:start.challenge_id,credential:registrationCredential(credential),name}),
 });
}

export async function reauthenticateSuperadminWithPasskey(){
 if(!superadminWebAuthnAvailable())throw new Error('Dieser Browser unterstützt die benötigte Passkey-Funktion nicht.');
 const start=await adminApi('/auth/reauth/passkey/options/',{method:'POST',body:'{}'});
 const credential=await navigator.credentials.get({publicKey:authenticationOptions(start.options)});
 if(!credential)throw new Error('Es wurde kein Passkey verwendet.');
 return adminApi('/auth/reauth/passkey/verify/',{
  method:'POST',
  body:JSON.stringify({challenge_id:start.challenge_id,credential:authenticationCredential(credential)}),
 });
}
