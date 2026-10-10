const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('app/src/main/assets/index.html','utf8');
assert.match(html, /id="nav"/);assert.match(html,/id="content"/);
const js=html.match(/<script>([\s\S]*?)<\/script>/)[1];new vm.Script(js);
const store=new Map(),calls=[],els={};
const get=id=>els[id] ||= {innerHTML:'',value:'',checked:false,textContent:'',classList:{toggle(){},remove(){}}};
const bridge={listProfiles(...x){calls.push(['listProfiles',...x])},searchProvider(...x){calls.push(['searchProvider',...x])},saveProfile(...x){calls.push(['saveProfile',...x])},open(...x){calls.push(['open',...x])},auditWebsite(...x){calls.push(['auditWebsite',...x])}};
const ctx=vm.createContext({document:{getElementById:get,querySelectorAll(){return []}},window:{Nova:bridge},Nova:bridge,localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},alert(){},confirm(){return true},console,Date,JSON,encodeURIComponent,decodeURIComponent});
const run=x=>vm.runInContext(x,ctx);
vm.runInContext(js,ctx);
for(const t of ['Overview','Jobs','BugHunter','Applications','Learn','Audit','Settings']){run(`show('${t}')`);assert.ok(get('content').innerHTML.length>80,`${t} empty`);console.log('PASS tab',t)}
run("show('Jobs')");get('q').value='help desk';get('location').value='Cleveland, OH';run('searchJobs()');assert.equal(calls.at(-1)[0],'searchProvider');assert.equal(calls.at(-1)[3],'Cleveland, OH');console.log('PASS location passed to search');
const id=calls.at(-1)[4];run(`novaProviderResult(${id},true,${JSON.stringify(JSON.stringify({jobs:[{id:1,title:'Help desk',company_name:'Acme',candidate_required_location:'Remote',job_type:'full_time',url:'https://example.com/1',description:'Support'}]}))})`);assert.match(get('content').innerHTML,/Help desk/);console.log('PASS provider response renders');
run('saveJob(0)');assert.equal(JSON.parse(store.get('nova.saved')).length,1);run("changeStatus(0,'Interview')");assert.equal(JSON.parse(store.get('nova.saved'))[0].status,'Interview');run('removeJob(0)');assert.equal(JSON.parse(store.get('nova.saved')).length,0);console.log('PASS application tracking');
run("show('BugHunter')");get('bn').value='Example';get('bu').value='https://example.com';run('addBounty()');assert.equal(JSON.parse(store.get('nova.bounties')).length,1);run('removeBounty(0)');assert.equal(JSON.parse(store.get('nova.bounties')).length,0);console.log('PASS bounty notes');
run("show('Audit')");get('auditTarget').value='https://example.com';get('auditConsent').checked=true;run('runAudit()');assert.equal(calls.at(-1)[0],'auditWebsite');console.log('PASS audit dispatch');
console.log('PASS JS syntax and smoke tests');
