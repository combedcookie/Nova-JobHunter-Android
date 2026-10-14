// ECLIPSE_V44_WORKBENCH: all tests are local. No network requests.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('app/src/main/assets/index.html','utf8');
const java=fs.readFileSync('app/src/main/java/com/nova/jobhunter/MainActivity.java','utf8');
const wf=fs.readFileSync('.github/workflows/build-apk.yml','utf8');
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
function mock(){
 const nodes={},sent=[],store=new Map();const el=id=>nodes[id]||=( {value:'',textContent:'',innerHTML:'',checked:false,classList:{toggle(){},remove(){}},setAttribute(){},append(){},focus(){}} );
 const Nova={eclipseV44Request(...a){sent.push(['request',...a])},eclipseV44History(...a){sent.push(['history',...a])},eclipseV44Cancel(...a){sent.push(['cancel',...a])},eclipseV44Clear(...a){sent.push(['clear',...a])},listProfiles(){},searchProvider(){}};
 const ctx=vm.createContext({window:{Nova,addEventListener(){}},Nova,document:{getElementById:el,querySelectorAll(){return []},body:{setAttribute(){}}},
   localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},console,Date,JSON,URL,Number,Math,Set,Map,Promise,encodeURIComponent,decodeURIComponent,alert(){},confirm(){return true},prompt(){return null},setTimeout(){return 0},clearTimeout(){}});
 for(const src of scripts)vm.runInContext(src,ctx);
 return {el,sent,store,run:code=>vm.runInContext(code,ctx)};
}
test('V4.4 workbench renders in Eclipse with separate offline lab',()=>{
 const x=mock();x.run("show('Eclipse')");assert.match(x.el('content').innerHTML,/Live workbench/);
 x.run("show('Eclipse Live')");assert.match(x.el('content').innerHTML,/OWNER-AUTHORIZED RESEARCH/);
 x.run("show('Security Lab')");assert.match(x.el('content').innerHTML,/Offline authorization workbench/);
});
test('no network dispatch without explicit checkbox',()=>{
 const x=mock();x.el('e44Scope').value='httpbin.org';x.el('e44Target').value='https://httpbin.org/get';x.el('e44Method').value='GET';
 x.run('eclipseV44Propose()');assert.equal(x.sent.filter(y=>y[0]==='request').length,0);
 assert.match(x.el('e44Result').textContent,/authorization box/);
});
test('reject wrong scope, user info, query, port, private hosts, and wildcard',()=>{
 const bad=['https://example.org/','https://httpbin.org/get?token=a','https://user@httpbin.org/','https://httpbin.org:8443/','https://httpbin.org/%2e%2e/x'];
 for(const url of bad){const x=mock();x.el('e44Scope').value='httpbin.org';x.el('e44Target').value=url;x.el('e44Method').value='HEAD';x.el('e44Consent').checked=true;x.run('eclipseV44Propose()');assert.equal(x.sent.filter(y=>y[0]==='request').length,0,url)}
 const x=mock();assert.equal(x.run("eclipseV44ValidHostname('192.168.1.1')"),false);assert.equal(x.run("eclipseV44ValidHostname('*.example.com')"),false);assert.equal(x.run("eclipseV44ValidHostname('dev.local')"),false);
});
test('one valid, manually consented request reaches native approval only once',()=>{
 const x=mock();x.el('e44Scope').value='httpbin.org';x.el('e44Target').value='https://httpbin.org/get';x.el('e44Method').value='GET';x.el('e44Consent').checked=true;
 x.run('eclipseV44Propose()');x.run('eclipseV44Propose()');const sent=x.sent.filter(y=>y[0]==='request');assert.equal(sent.length,1);assert.equal(sent[0][1],'https://httpbin.org/get');assert.equal(sent[0][2],'httpbin.org');assert.equal(sent[0][3],'GET');
 x.run('eclipseV44Cancel()');assert.equal(x.sent.filter(y=>y[0]==='cancel').length,1);
});
test('AutoFind handoff preloads only research references, never permission or asset host',()=>{
 const x=mock();x.store.set('nova.h1.active.v2',JSON.stringify({name:'Demo bounty program',url:'https://hackerone.com/demo',scope:'private.example'}));
 x.el('e44Consent').checked=true;x.run('eclipseV44LoadDraft()');
 assert.equal(x.el('e44Program').value,'Demo bounty program');
 assert.equal(x.el('e44Policy').value,'https://hackerone.com/demo');
 assert.equal(x.el('e44Scope').value,'');assert.equal(x.el('e44Consent').checked,false);
});
test('scope draft never persists checkbox approval',()=>{
 const x=mock();x.el('e44Scope').value='httpbin.org';x.el('e44Policy').value='https://hackerone.com/policy';x.el('e44Program').value='Test';x.el('e44Consent').checked=true;
 x.run('eclipseV44SaveDraft()');assert.ok(x.store.has('nova.eclipse.v44.scope.draft'));
 x.run('eclipseV44LoadDraft()');assert.equal(x.el('e44Consent').checked,false);
});
test('stale results cannot complete a newer request; raw body is never presented',()=>{
 const x=mock();x.el('e44Scope').value='httpbin.org';x.el('e44Target').value='https://httpbin.org/';x.el('e44Method').value='HEAD';x.el('e44Consent').checked=true;
 x.run('eclipseV44Propose()');const id=x.sent.filter(v=>v[0]==='request')[0][4];
 x.run(`eclipseV44Result(${id+10},false,'wrong request')`);assert.equal(x.run('eclipseV44Active'),id);
 const p=JSON.stringify({environment:'approved_live_https',host:'httpbin.org',path:'/',method:'HEAD',status:200,headers_present:['Strict-Transport-Security'],sample_bytes:0,sample_sha256:'',sample_truncated:false,body:'RAW_SECRET_SHOULD_NOT_APPEAR',note:'metadata'});
 x.run(`eclipseV44Result(${id},true,${JSON.stringify(p)})`);
 assert.equal(x.run('eclipseV44Active'),0);assert.match(x.el('e44Result').textContent,/HTTP|\"status\"/);assert.doesNotMatch(x.el('e44Result').textContent,/RAW_SECRET/);
});
test('native evidence includes bounded retention and excludes raw response bodies',()=>{
 assert.match(java,/ORDER BY id DESC LIMIT 100/);assert.match(java,/SELECT id,at_ms,host,path,method,status,sample_bytes,sample_sha256,sample_truncated,headers_json/);
 assert.doesNotMatch(java,/values\.put\(\"response_body\"/);
 assert.match(java,/java\.net\.HttpURLConnection c=job\.connection/);
 assert.match(java,/\.setNegativeButton\(\"Reject\"/);
});
test('native approval and evidence paths enforced in Java, not AI prompts',()=>{
 assert.match(java,/ECLIPSE_V44_NATIVE_HTTP/);
 for(const method of ['eclipseV44Request','eclipseV44Cancel','eclipseV44History','eclipseV44Clear'])assert.match(java,new RegExp('@JavascriptInterface public void '+method+'\\('));
 assert.match(java,/\.setPositiveButton\("Approve once"/);
 assert.match(java,/\.setInstanceFollowRedirects\(false\)/);
 assert.match(java,/getRawQuery\(\)!=null/);
 assert.match(java,/java\.net\.Proxy\.NO_PROXY/);
 assert.match(java,/eclipseV44CheckPublicDns/);
 assert.match(java,/CREATE TABLE evidence/);
 assert.match(java,/eclipseV44SaveEvidence\(result\)/);
 assert.match(java,/sample_truncated/);
 assert.match(wf,/test-eclipse-v44\.cjs/);
});
test('redacted evidence history safely escapes HTML',()=>{
 const x=mock();x.run("show('Eclipse Live')");const id=x.sent.filter(y=>y[0]==='history').at(-1)[1];
 const data=JSON.stringify([{id:1,at_ms:1,host:'<img src=x onerror=alert(1)>',path:'/',method:'GET',status:200,sample_bytes:0,sample_sha256:''}]);
 x.run(`eclipseV44HistoryResult(${id},true,${JSON.stringify(data)})`);
 assert.doesNotMatch(x.el('e44History').innerHTML,/<img src=x/);
 assert.match(x.el('e44History').innerHTML,/&lt;img/);
});
