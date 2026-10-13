import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {api} from './api';
import './vehicles.css';

const attribution='<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a>';

export default function VehicleMap({familyId,points=[]}){
 const {t}=useTranslation();
 const container=useRef(null),map=useRef(null),latest=useRef(points);
 const [error,setError]=useState(''),[loading,setLoading]=useState(true);
 latest.current=points;
 function update(){
  const instance=map.current;if(!instance?.getSource('route'))return;
  const coordinates=latest.current.map(p=>[p.longitude,p.latitude]);
  instance.getSource('route').setData({type:'FeatureCollection',features:coordinates.length?[{type:'Feature',properties:{},geometry:{type:'LineString',coordinates:coordinates.length===1?[coordinates[0],coordinates[0]]:coordinates}}]:[]});
  if(coordinates.length){
   const lngs=coordinates.map(p=>p[0]),lats=coordinates.map(p=>p[1]);
   instance.fitBounds([[Math.min(...lngs),Math.min(...lats)],[Math.max(...lngs),Math.max(...lats)]],{padding:35,maxZoom:15,duration:0});
  }
 }
 useEffect(()=>{
  let live=true;
  Promise.all([
   import('maplibre-gl'),
   import('maplibre-gl/dist/maplibre-gl.css'),
   import('maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'),
   api(`/vehicles/map-config/?family=${encodeURIComponent(familyId)}`),
  ]).then(([module,,worker,config])=>{
   if(!live)return;
   const MapLibre=module;
   // Bundle the module worker as a first-party asset: production CSP stays worker-src self.
   MapLibre.setWorkerUrl(worker.default);
   const sources={},layers=[{id:'background',type:'background',paint:{'background-color':'#eef2ef'}}];
   if(config.configured){
    sources.base={type:'raster',tiles:[config.tile_url],tileSize:256,maxzoom:19,attribution};
    layers.push({id:'base',type:'raster',source:'base'});
   }else setError(t('vehiclesUi.mapMissing'));
   const instance=new MapLibre.Map({
    container:container.current,
    // OSM gets the app origin only, never private query parameters or authentication cookies.
    transformRequest:(url,type)=>type==='Tile'?{url,credentials:'omit',cache:'default',referrerPolicy:'origin'}:{url},
    style:{version:8,sources,layers},center:[10.5,51],zoom:5,attributionControl:false,
   });
   map.current=instance;
   instance.addControl(new MapLibre.AttributionControl({compact:false}));
   instance.addControl(new MapLibre.NavigationControl({showCompass:false}));
   instance.on('error',()=>{if(live){setLoading(false);setError(t('vehiclesUi.mapError'))}});
   instance.on('load',()=>{
    if(!live)return;setLoading(false);
    instance.addSource('route',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
    instance.addLayer({id:'route-line',type:'line',source:'route',paint:{'line-color':'#2563eb','line-width':4}});
    update();
   });
  }).catch(()=>{if(live){setLoading(false);setError(t('vehiclesUi.mapError'))}});
  return()=>{live=false;map.current?.remove();map.current=null};
 },[familyId,t]);
 useEffect(()=>{update()},[points]);
 return <section aria-label={t('vehiclesUi.route')}>{loading&&<p role="status">{t('vehiclesUi.mapLoading')}</p>}{error&&<p role="status">{error}</p>}<div ref={container} className="vehicle-map"/></section>;
}
