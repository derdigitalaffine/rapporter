import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {FEATURE_REGISTRY} from '../src/feature-registry.js';
import {pageFromLocation,pageHref} from '../src/navigation.js';

// Optional isolated experiment: no router dependency is added to production.
if(!process.argv[2])throw new Error('Pass the absolute path to an isolated react-router dist/production/index.js');
const {createMemoryRouter,matchRoutes}=await import(pathToFileURL(process.argv[2]));
const routes=[{path:'/',id:'shell'},...['/invite/:token','/verify-email/:token','/reset-password/:uid/:token'].map(path=>({path,id:path}))];
for(const {id} of FEATURE_REGISTRY){
  const url=`/?page=${id}`;
  assert.equal(matchRoutes(routes,url)?.at(-1)?.route.id,'shell');
  assert.equal(pageFromLocation(new URL(url,'https://example.test').search),id);
}
for(const path of ['/invite/example','/verify-email/example','/reset-password/uid/example'])assert.ok(matchRoutes(routes,path));
const router=createMemoryRouter(routes,{initialEntries:['/?page=home']});
await router.navigate('/?page=trips');
await router.navigate('/?page=trips',{state:{createFlow:'event'}});
assert.equal(router.state.location.state.createFlow,'event');
await router.navigate(-1);
assert.equal(router.state.location.search,'?page=trips');
assert.equal(router.state.location.state,null);
await router.navigate(-1);
assert.equal(router.state.location.search,'?page=home');
await router.navigate(1);
assert.equal(router.state.location.search,'?page=trips');
assert.equal(pageHref('more','https://example.test/?page=expenses&expense=example'),'/?page=more');
router.dispose();
console.log('Router spike: 30 query routes resolve to one pathname route; special paths and same-URL overlay history are compatible but require existing registry/query/guard semantics. Retain the current Navigation Service; no parallel router state.');
