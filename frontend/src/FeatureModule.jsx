import {Component,createContext,lazy,Suspense,useContext,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {FEATURE_REGISTRY,featureAvailability} from './feature-registry';
import {Icon} from './icons';
import './feature-loading-i18n';
import StatisticsAccessState from './StatisticsAccessState';
import {hasDirtyState} from './dirty-state';

export const FeatureAvailabilityContext=createContext({});
class ChunkBoundary extends Component{
  constructor(props){super(props);this.state={error:null}}
  static getDerivedStateFromError(error){return {error}}
  render(){return this.state.error?this.props.fallback:this.props.children}
}
function FeatureState({kind,onRetry,onBack}){
  const {t}=useTranslation();
  return <section className="smart-empty app-load-state" role={kind==='pending'?'status':'alert'} aria-busy={kind==='pending'}>
    <Icon name={kind==='pending'?'refresh':'warning'} size={34}/><strong>{t(`featureLoading.${kind}`)}</strong>
    {onRetry&&<button type="button" className="secondary compact" onClick={onRetry}><Icon name="refresh"/>{t('featureLoading.retry')}</button>}
    {kind==='failed'&&<button type="button" className="text-button" onClick={()=>navigator.serviceWorker?.getRegistration().then(registration=>registration?.update()).catch(()=>{})}>{t('featureLoading.update')}</button>}
    {kind==='failed'&&<button type="button" className="text-button" onClick={()=>{const event=new CustomEvent('famuhle:before-navigation',{cancelable:true,detail:{reload:true}});window.dispatchEvent(event);if(!event.defaultPrevented&&!hasDirtyState())location.reload();}}>{t('featureLoading.reload')}</button>}
    {onBack&&<button type="button" className="text-button" onClick={onBack}><Icon name="back"/>{t('back')}</button>}
  </section>;
}
export function DeferredModule({load,onBack,...props}){
  const [attempt,setAttempt]=useState(()=>({Component:lazy(load),id:0}));
  const Content=attempt.Component;
  return <ChunkBoundary key={attempt.id} fallback={<FeatureState kind={navigator.onLine===false?'offline':'failed'} onRetry={()=>setAttempt(previous=>({Component:lazy(load),id:previous.id+1}))} onBack={onBack}/>}>
    <Suspense fallback={<FeatureState kind="pending" onBack={onBack}/>}><Content {...props} onBack={onBack}/></Suspense>
  </ChunkBoundary>;
}
function registeredComponent(feature){
  return function RegisteredFeature(props){
    const context=useContext(FeatureAvailabilityContext);
    const availability=featureAvailability(feature.id,context);
    if(availability!=='available')return feature.id==='statistics'?<StatisticsAccessState kind={availability} onBack={props.onBack}/>:<FeatureState kind={availability} onBack={props.onBack}/>;
    return <DeferredModule load={feature.load} {...props}/>;
  };
}
// One registry owns dynamic imports. App binds these adapters to its existing props.
export const FEATURE_COMPONENTS=Object.freeze(Object.fromEntries(FEATURE_REGISTRY.filter(feature=>feature.load).map(feature=>[feature.id,registeredComponent(feature)])));
