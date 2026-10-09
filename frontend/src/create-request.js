export const CREATE_REQUEST_EVENT='famuhle:create-request';

export function requestCreate(id,context={}){
  window.dispatchEvent(new CustomEvent(CREATE_REQUEST_EVENT,{detail:{id,context}}));
}
