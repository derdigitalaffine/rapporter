import {api,markAuthenticated} from './api';

export class PasskeyCancelledError extends Error{
 constructor(){super('passkey_cancelled');this.name='PasskeyCancelledError'}
}

export class PasskeyUnsupportedError extends Error{
 constructor(){super('passkey_unsupported');this.name='PasskeyUnsupportedError'}
}

export function isPasskeySupported(){
 return typeof window!=='undefined'&&Boolean(window.isSecureContext)&&typeof window.PublicKeyCredential!=='undefined'&&typeof navigator!=='undefined'&&Boolean(navigator.credentials);
}

export function isPasskeyCancellation(error){return error instanceof PasskeyCancelledError||error?.name==='NotAllowedError'||error?.name==='AbortError'}

function requireSupport(){if(!isPasskeySupported())throw new PasskeyUnsupportedError()}

function base64urlToBytes(value){
 const normalized=String(value||'').replace(/-/g,'+').replace(/_/g,'/');
 const padded=normalized+'='.repeat((4-normalized.length%4)%4);
 const binary=atob(padded);const bytes=new Uint8Array(binary.length);
 for(let index=0;index<binary.length;index+=1)bytes[index]=binary.charCodeAt(index);
 return bytes;
}

function bytesToBase64url(value){
 if(value==null)return null;
 const bytes=value instanceof Uint8Array?value:new Uint8Array(value);
 let binary='';for(let index=0;index<bytes.byteLength;index+=1)binary+=String.fromCharCode(bytes[index]);
 return btoa(binary).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}

function descriptorFromJSON(item){return {...item,id:base64urlToBytes(item.id)}}

function creationOptionsFromJSON(options){
 if(typeof window.PublicKeyCredential?.parseCreationOptionsFromJSON==='function')return window.PublicKeyCredential.parseCreationOptionsFromJSON(options);
 return {
  ...options,
  challenge:base64urlToBytes(options.challenge),
  user:{...options.user,id:base64urlToBytes(options.user.id)},
  excludeCredentials:(options.excludeCredentials||[]).map(descriptorFromJSON),
 };
}

function requestOptionsFromJSON(options){
 if(typeof window.PublicKeyCredential?.parseRequestOptionsFromJSON==='function')return window.PublicKeyCredential.parseRequestOptionsFromJSON(options);
 return {
  ...options,
  challenge:base64urlToBytes(options.challenge),
  allowCredentials:(options.allowCredentials||[]).map(descriptorFromJSON),
 };
}

function credentialToJSON(credential){
 const response=credential.response;const serialized={
  id:credential.id,
  rawId:bytesToBase64url(credential.rawId),
  type:credential.type,
  response:{clientDataJSON:bytesToBase64url(response.clientDataJSON)},
 };
 if(credential.authenticatorAttachment)serialized.authenticatorAttachment=credential.authenticatorAttachment;
 const extensions=credential.getClientExtensionResults?.();if(extensions&&Object.keys(extensions).length)serialized.clientExtensionResults=extensions;
 if(response.attestationObject)serialized.response.attestationObject=bytesToBase64url(response.attestationObject);
 if(response.authenticatorData)serialized.response.authenticatorData=bytesToBase64url(response.authenticatorData);
 if(response.signature)serialized.response.signature=bytesToBase64url(response.signature);
 if(response.userHandle)serialized.response.userHandle=bytesToBase64url(response.userHandle);
 const transports=response.getTransports?.();if(Array.isArray(transports)&&transports.length)serialized.response.transports=transports;
 return serialized;
}

async function createCredential(options){
 requireSupport();
 try{
  const credential=await navigator.credentials.create({publicKey:creationOptionsFromJSON(options)});
  if(!credential)throw new PasskeyCancelledError();
  return credentialToJSON(credential);
 }catch(error){if(isPasskeyCancellation(error))throw new PasskeyCancelledError();throw error}
}

async function getCredential(options){
 requireSupport();
 try{
  const credential=await navigator.credentials.get({publicKey:requestOptionsFromJSON(options)});
  if(!credential)throw new PasskeyCancelledError();
  return credentialToJSON(credential);
 }catch(error){if(isPasskeyCancellation(error))throw new PasskeyCancelledError();throw error}
}

export async function loginWithPasskey(){
 const challenge=await api('/auth/passkeys/authentication/options/',{method:'POST',body:'{}'});
 const credential=await getCredential(challenge.options);
 const result=await api('/auth/passkeys/authentication/verify/',{method:'POST',body:JSON.stringify({challenge_id:challenge.challenge_id,credential})});
 markAuthenticated(true);
 return result;
}

export async function listPasskeys(){return api('/auth/passkeys/')}

export async function registerPasskey(name){
 const challenge=await api('/auth/passkeys/registration/options/',{method:'POST',body:'{}'});
 const credential=await createCredential(challenge.options);
 return api('/auth/passkeys/registration/verify/',{method:'POST',body:JSON.stringify({challenge_id:challenge.challenge_id,credential,name})});
}

export async function reauthenticateWithPasskey(){
 const challenge=await api('/auth/passkeys/reauth/options/',{method:'POST',body:'{}'});
 const credential=await getCredential(challenge.options);
 return api('/auth/passkeys/reauth/verify/',{method:'POST',body:JSON.stringify({challenge_id:challenge.challenge_id,credential})});
}

export async function renamePasskey(id,name){return api(`/auth/passkeys/${encodeURIComponent(id)}/`,{method:'PATCH',body:JSON.stringify({name})})}
export async function removePasskey(id){return api(`/auth/passkeys/${encodeURIComponent(id)}/`,{method:'DELETE'})}
