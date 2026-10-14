// Eclipse V4.4.1: offline tests only; no real network requests or model execution.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('app/src/main/assets/index.html','utf8');
const java=fs.readFileSync('app/src/main/java/com/nova/jobhunter/MainActivity.java','utf8');
const manifest=fs.readFileSync('app/src/main/AndroidManifest.xml','utf8');
const gradle=fs.readFileSync('app/build.gradle','utf8');
const wf=fs.readFileSync('.github/workflows/build-apk.yml','utf8');
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
function mock(){
 const store=new Map(),sent=[],nodes={};
 const el=id=>nodes[id]||=({value:'',textContent:'',innerHTML:'',checked:false,disabled:false,tagName:'INPUT',classList:{toggle(){},remove(){},add(){}},setAttribute(){},append(){},focus(){}});
 const Nova={eclipseV44Request(...x){sent.push(['request',...x])},eclipseV44History(...x){sent.push(['history',...x])},eclipseV44Cancel(...x){sent.push(['cancel',...x])},eclipseV44Clear(...x){sent.push(['clear',...x])},eclipseV441Ask(...x){sent.push(['ai',...x])},eclipseV441CancelAi(...x){sent.push(['ai_cancel',...x])},listProfiles(){},searchProvider(){}};
 const document={getElementById:el,querySelectorAll(){return []},addEventListener(){},body:{classList:{add(){},remove(){}},setAttribute(){}}};
 const ctx=vm.createContext({window:{Nova,addEventListener(){}},Nova,document,localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},console,Date,JSON,URL,Number,Math,Set,Map,Promise,encodeURIComponent,decodeURIComponent,setTimeout(){return 0},clearTimeout(){},alert(){},confirm(){return true},prompt(){return null}});
 for(const script of scripts)vm.runInContext(script,ctx);
 return {el,sent,store,run:code=>vm.runInContext(code,ctx)};
}
test('native root, version and Android viewport avoid overlapping OS bars',()=>{
 assert.match(java,/ECLIPSE_V441_SAFE_ROOT/);assert.match(java,/setContentView\(eclipseV441SafeRoot\)/);
 assert.match(java,/WindowInsets\.Type\.ime\(\)/);assert.doesNotMatch(java,/web\.setOnApplyWindowInsetsListener/);
 assert.match(html,/nova-eclipse-v441-safe-layout/);assert.match(html,/body\{padding-top:0!important;padding-bottom:0!important/);
 assert.match(manifest,/windowSoftInputMode="adjustResize"/);assert.match(manifest,/android:label="NOVA Board"/);assert.match(gradle,/versionCode 7/);
});
test('workbench has local-model Eclipse assistant with no approval shortcut',()=>{
 const x=mock();x.run("show('Eclipse Live')");const s=x.el('content').innerHTML;
 assert.match(s,/Eclipse AI · live investigation copilot/);assert.match(s,/approved again on Android/);
 assert.match(s,/e441Use/);assert.match(s,/e44Consent/);
});
test('Eclipse planning cannot execute a request even with convincing answer',()=>{
 const x=mock();x.el('e44Scope').value='httpbin.org';x.el('e441Question').value='Recommend the root path';
 x.run("eclipseV441Ask('plan')");const call=x.sent.find(y=>y[0]==='ai');assert.ok(call);
 x.run(`eclipseV441AiResult(${call[2]},true,"RATIONALE: safe test\\nMETHOD: HEAD\\nPATH: /get\\nUNKNOWN: owner must verify scope")`);
 assert.equal(x.sent.filter(y=>y[0]==='request').length,0);assert.equal(x.el('e441Use').disabled,false);
 x.el('e44Consent').checked=true;x.run('eclipseV441UseProposal()');
 assert.equal(x.el('e44Target').value,'https://httpbin.org/get');assert.equal(x.el('e44Method').value,'HEAD');assert.equal(x.el('e44Consent').checked,false);
 assert.equal(x.sent.filter(y=>y[0]==='request').length,0);
});
test('host changes invalidate AI proposal before application',()=>{
 const x=mock();x.el('e44Scope').value='httpbin.org';x.el('e441Question').value='root';x.run("eclipseV441Ask('plan')");const call=x.sent.find(y=>y[0]==='ai');
 x.run(`eclipseV441AiResult(${call[2]},true,"METHOD: HEAD\\nPATH: /")`);
 x.el('e44Scope').value='example.net';x.run('eclipseV441UseProposal()');
 assert.equal(x.el('e44Target').value,'');assert.equal(x.sent.filter(y=>y[0]==='request').length,0);
});
test('unsafe or unstructured model output cannot become a request',()=>{
 const x=mock();
 for(const text of ['METHOD: GET\nPATH: /','METHOD: HEAD\nPATH: /admin?access=1','METHOD: HEAD\nPATH: /%2e%2e/private','METHOD: HEAD\nPATH: //evil.example/']){
  assert.equal(x.run(`eclipseV441ExtractProposal(${JSON.stringify(text)},'httpbin.org')`),null);
 }
 assert.equal(x.run("eclipseV441ExtractProposal('METHOD: HEAD\\nPATH: /get','httpbin.org')?.path"),'/get');
});
test('host edited during AI inference cannot turn old suggestion into new-target request',()=>{
 const x=mock();x.el('e44Scope').value='httpbin.org';x.run("eclipseV441Ask('plan')");const id=x.sent.find(y=>y[0]==='ai')[2];
 x.el('e44Scope').value='example.net';x.run(`eclipseV441AiResult(${id},true,"METHOD: HEAD\\nPATH: /get")`);
 assert.equal(x.run('eclipseV441Proposal'),null);assert.equal(x.sent.filter(y=>y[0]==='request').length,0);
});
test('reopening history provides analyzable metadata without raw body',()=>{
 const x=mock();x.run("show('Eclipse Live')");const id=x.sent.filter(y=>y[0]==='history').at(-1)[1];
 const rows=JSON.stringify([{id:1,at_ms:9,host:'httpbin.org',path:'/get',method:'HEAD',status:200,sample_bytes:0,headers_present:['Content-Type'],sample_sha256:''}]);
 x.run(`eclipseV44HistoryResult(${id},true,${JSON.stringify(rows)})`);
 x.run("eclipseV441Ask('analyze')");assert.equal(x.sent.filter(y=>y[0]==='ai').length,1);
});
test('planning rejects missing scope and analysis rejects missing evidence',()=>{
 const x=mock();x.run("eclipseV441Ask('plan')");x.run("eclipseV441Ask('analyze')");
 assert.equal(x.sent.filter(y=>y[0]==='ai').length,0);
});
test('real approved metadata can be analyzed but never raw response body',()=>{
 const x=mock();x.el('e44Scope').value='httpbin.org';
 x.run("eclipseV441CaptureResult({environment:'approved_live_https',method:'HEAD',host:'httpbin.org',path:'/get',status:200,at_ms:3,headers_present:['Content-Type'],sample_bytes:0,body:'SECRET SHOULD NOT PASS'})");
 x.run("eclipseV441Ask('analyze')");const call=x.sent.find(y=>y[0]==='ai');assert.ok(call);
 assert.match(call[1],/HTTP|status|200/);assert.doesNotMatch(call[1],/SECRET SHOULD NOT PASS/);
});
test('Eclipse AI rejects stale result IDs and does not trigger execution',()=>{
 const x=mock();x.el('e44Scope').value='httpbin.org';x.run("eclipseV441Ask('plan')");const id=x.sent.find(y=>y[0]==='ai')[2];
 x.run(`eclipseV441AiResult(${id+1},true,"METHOD: HEAD\\nPATH: /evil")`);
 assert.equal(x.el('e441Use').disabled,true);
 assert.equal(x.run('eclipseV441AiActive'),id);
 x.run(`eclipseV441AiResult(${id},false,'Import a local model first')`);
 assert.equal(x.run('eclipseV441AiActive'),0);assert.equal(x.sent.filter(y=>y[0]==='request').length,0);
});
test('checkbox must be rechecked each time a request is proposed',()=>{
 const x=mock();x.el('e44Scope').value='httpbin.org';x.el('e44Target').value='https://httpbin.org/get';x.el('e44Method').value='HEAD';x.el('e44Consent').checked=true;
 x.run('eclipseV44Propose()');assert.equal(x.el('e44Consent').checked,false);
 assert.equal(x.sent.filter(y=>y[0]==='request').length,1);
});
test('native cancellation keeps slot until live worker disconnects',()=>{
 assert.match(java,/volatile boolean started=false/);assert.match(java,/if\(!job\.started\)eclipseV44Finish/);
 assert.match(java,/if\(c!=null\)c\.disconnect\(\);job\.connection=null;[\s\S]{0,160}eclipseV44Finish\(job,success&&!job\.cancelled/);
});
test('shared GGUF concurrency lock and separate callback are native',()=>{
 assert.match(java,/eclipseV441Ask\(String prompt,int id\)/);
 assert.match(java,/generationBusy\.compareAndSet\(false,true\)/);
 assert.match(java,/reply\("eclipseV441AiResult",id,true,answer\)/);
 assert.match(java,/eclipseV441CancelAi\(int id\)/);
 assert.match(wf,/test-eclipse-v441\.cjs/);
});
