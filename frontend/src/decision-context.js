import {featureHref} from './navigation.js';

const PRESETS={
  shopping_list:{
    en:[
      {key:'purchase',label:'Plan a purchase',question:'Which option should we buy?',mode:'ranking'},
      {key:'meal',label:'What should we eat?',question:'What should we eat?',mode:'single'},
    ],
    de:[
      {key:'purchase',label:'Anschaffung planen',question:'Welche Option sollen wir anschaffen?',mode:'ranking'},
      {key:'meal',label:'Was wollen wir essen?',question:'Was wollen wir essen?',mode:'single'},
    ],
  },
  trip:{
    en:[
      {key:'destination',label:'Choose destination',question:'Where should we travel?',mode:'ranking'},
      {key:'stay',label:'Choose accommodation',question:'Which accommodation suits us best?',mode:'rating'},
      {key:'activity',label:'Choose activities',question:'What do we want to do there?',mode:'multiple'},
    ],
    de:[
      {key:'destination',label:'Reiseziel abstimmen',question:'Wohin wollen wir reisen?',mode:'ranking'},
      {key:'stay',label:'Unterkunft abstimmen',question:'Welche Unterkunft passt am besten zu uns?',mode:'rating'},
      {key:'activity',label:'Aktivitäten abstimmen',question:'Was wollen wir vor Ort machen?',mode:'multiple'},
    ],
  },
};

export function decisionPresetsFor(type,en=false){
  return PRESETS[type]?.[en?'en':'de']||[];
}

export function decisionContextHref(context,preset=''){
  return featureHref('decisions',{
    decision_context_type:context?.type||null,
    decision_context_id:context?.id||null,
    decision_preset:preset||null,
  },'http://localhost/');
}

export function decisionContextFromSearch(search=''){
  const params=new URLSearchParams(search);
  const type=params.get('decision_context_type')||'';
  const id=params.get('decision_context_id')||'';
  return type&&id?{type,id}:null;
}

export function decisionPresetDraft(search='',en=false){
  const context=decisionContextFromSearch(search);
  if(!context)return null;
  const key=new URLSearchParams(search).get('decision_preset')||'';
  const preset=decisionPresetsFor(context.type,en).find(item=>item.key===key);
  if(!preset)return null;
  return {question:preset.question,mode:preset.mode,anonymous:false,closes_at:'',options:['','']};
}

export function decisionContextClearedHref(current,decision=null){
  return featureHref('decisions',{
    decision:decision||null,
    decision_context_type:null,
    decision_context_id:null,
    decision_preset:null,
  },current);
}
