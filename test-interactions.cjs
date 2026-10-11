const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const html=fs.readFileSync('app/src/main/assets/index.html','utf8');
const script=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).find(s=>/function\s+show\s*\(/.test(s));
const functions=new Set([...script.matchAll(/\bfunction\s+(\w+)\s*\(/g)].map(x=>x[1]));
const native=new Set([...fs.readFileSync('app/src/main/java/com/nova/jobhunter/MainActivity.java','utf8').matchAll(/@JavascriptInterface\s+public\s+\w+\s+(\w+)\s*\(/g)].map(x=>x[1]));
const actions=[...html.matchAll(/\bon(click|change|input|submit)="([^"]*)"/g)].map(x=>x[2]);
assert(actions.length>=20,`Expected 20+ inline handlers, found ${actions.length}`);
for(const a of actions){for(const m of a.matchAll(/(?:^|[;\s])([a-zA-Z_]\w*)\s*\(/g)){const fn=m[1];assert(functions.has(fn)||new RegExp('\\bfunction\\s+'+fn+'\\s*\\(').test(html)||['alert','confirm'].includes(fn),`Missing handler ${fn}`)}}
for(const m of html.matchAll(/\bNova\.(\w+)\s*\(/g))assert(native.has(m[1]),`Missing native bridge ${m[1]}`);
console.log('PASS inline event patterns',actions.length,'and Android bridge');
const els={},store=new Map(),calls=[];
const get=id=>els[id]||= {value:'',checked:false,textContent:'',classList:{toggle(){},remove(){}},get innerHTML(){return this._html||''},set innerHTML(s){this._html=s;if(id==='content'){for(const k of ['location','q','provider','status','results','sp','fields','profiles','configStatus','bn','bu','auditTarget','auditConsent','auditResult','work','type','salary','level'])delete els[k];}}};
const bridge={searchProvider(...x){calls.push(['searchProvider',...x])},listProfiles(...x){calls.push(['listProfiles',...x])},saveProfile(...x){calls.push(['saveProfile',...x])},activateProfile(...x){calls.push(['activateProfile',...x])},deleteProfile(...x){calls.push(['deleteProfile',...x])},open(...x){calls.push(['open',...x])},auditWebsite(...x){calls.push(['auditWebsite',...x])}};
const ctx=vm.createContext({document:{getElementById:get,querySelectorAll(){return []}},window:{Nova:bridge,addEventListener(){}},Nova:bridge,localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},alert(){},confirm(){return true},console,Date,JSON,URL,encodeURIComponent,decodeURIComponent});
const run=s=>vm.runInContext(s,ctx);
vm.runInContext(script,ctx);
for(const t of ['Overview','Jobs','BugHunter','Applications','Learn','Audit','Settings']){run(`show('${t}')`);assert(get('content').innerHTML.length>60);}
console.log('PASS seven screen renderings with DOM reset');
run("show('Jobs')");get('q').value='help desk';get('location').value='Cleveland, OH';run('searchJobs()');assert.equal(calls.at(-1)[3],'Cleveland, OH');console.log('PASS job location survives redraw');
const id=calls.at(-1)[4];run(`novaProviderResult(${id},true,${JSON.stringify(JSON.stringify({jobs:[{id:1,title:'Help desk',company_name:'Acme',url:'https://example.com/job',description:'Support'}]}))})`);
assert.match(get('content').innerHTML,/Help desk/);run('saveJob(0)');assert.equal(JSON.parse(store.get('nova.saved')).length,1);run("changeStatus(0,'Interview')");assert.equal(JSON.parse(store.get('nova.saved'))[0].status,'Interview');run('openSaved(0)');assert.equal(calls.at(-1)[0],'open');run('removeJob(0)');assert.equal(JSON.parse(store.get('nova.saved')).length,0);console.log('PASS tracking status, open, remove');
run("show('BugHunter')");get('bn').value='Test';get('bu').value='https://example.com';run('addBounty()');assert.equal(JSON.parse(store.get('nova.bounties')).length,1);run('removeBounty(0)');assert.equal(JSON.parse(store.get('nova.bounties')).length,0);console.log('PASS bounty notes');
run("show('Audit')");get('auditTarget').value='https://example.com';get('auditConsent').checked=true;run('runAudit()');assert.notEqual(calls.at(-1)[0],'auditWebsite');get('novaBountyConsent').checked=true;run('novaBountyApprove()');assert.equal(calls.at(-1)[0],'auditWebsite');console.log('PASS audit dispatch');
run("show('Settings')");assert.equal(calls.at(-1)[0],'listProfiles');console.log('PASS settings refresh dispatch');
