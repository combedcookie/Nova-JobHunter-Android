// Eclipse V4.4.2 chat proposal/deny/modify/approval workflow, purely offline.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync('app/src/main/assets/index.html','utf8');
const java=fs.readFileSync('app/src/main/java/com/nova/jobhunter/MainActivity.java','utf8');
const gradle=fs.readFileSync('app/build.gradle','utf8');
const wf=fs.readFileSync('.github/workflows/build-apk.yml','utf8');
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(x=>x[1]);
function lab(){
 const store=new Map(),sent=[],nodes={};
 const el=id=>nodes[id]||=({value:'',textContent:'',innerHTML:'',checked:false,disabled:false,tagName:'INPUT',scrollTop:0,scrollHeight:0,focus(){},setAttribute(){},classList:{add(){},remove(){},toggle(){}}});
 const Nova={eclipseV44Request(...x){sent.push(['request',...x])},eclipseV44History(...x){sent.push(['history',...x])},eclipseV44Cancel(...x){sent.push(['cancel',...x])},eclipseV44Clear(...x){sent.push(['clear',...x])},eclipseV441Ask(...x){sent.push(['ai',...x])},eclipseV441CancelAi(...x){sent.push(['ai_cancel',...x])},novaCopilotPermission(){sent.push(['notify_permission'])}};
 const document={getElementById:el,querySelectorAll(){return []},addEventListener(){},body:{classList:{add(){},remove(){}},setAttribute(){}},activeElement:null};
 const storage={getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)};
 const context=vm.createContext({window:{Nova,addEventListener(){}},Nova,document,localStorage:storage,console,Date,JSON,URL,Number,Math,Set,Map,Promise,encodeURIComponent,decodeURIComponent,setTimeout(){return 0},clearTimeout(){},alert(){},confirm(){return true},prompt(){return null}});
 for(const script of scripts)vm.runInContext(script,context);
 return {el,sent,store,run:s=>vm.runInContext(s,context)};
}
function proposal(x,path='/get'){
 x.el('e44Scope').value='httpbin.org';x.el('e442Input').value='Suggest one safe HEAD check';
 x.run("eclipseV442Send('plan')");const a=x.sent.filter(t=>t[0]==='ai').at(-1);
 assert.ok(a,'local model must be invoked');assert.equal(x.sent.some(t=>t[0]==='request'),false);
 x.run(`eclipseV441AiResult(${a[2]},true,${JSON.stringify('RATIONALE: conservative HEAD\nMETHOD: HEAD\nPATH: '+path+'\nUNKNOWN: scope verification needed')})`);
}
test('chat UI offers Approve Deny Modify and retains manual native fallback',()=>{
 const x=lab();x.run("show('Eclipse Live')");const html=x.el('content').innerHTML;
 assert.match(html,/Eclipse AI · live investigation copilot/);assert.match(html,/e442Thread/);assert.match(html,/e442Input/);
 assert.match(html,/e44Consent/);assert.match(html,/e44Target/);assert.match(html,/e442Advanced/);
 assert.match(fs.readFileSync('app/src/main/assets/index.html','utf8'),/eclipseV442Approve\(\)/);
 assert.match(fs.readFileSync('app/src/main/assets/index.html','utf8'),/eclipseV442Deny\(\)/);
 assert.match(fs.readFileSync('app/src/main/assets/index.html','utf8'),/eclipseV442Modify\(\)/);
});
test('chat planning shows reviewable proposal but never launches a request',()=>{
 const x=lab();proposal(x);
 assert.match(x.el('e442Thread').innerHTML,/HEAD https:\/\/httpbin.org\/get/);
 assert.equal(x.sent.filter(t=>t[0]==='request').length,0);
 assert.match(x.el('e442Thread').innerHTML,/Approve/);
});
test('Approving without independently checking per-proposal consent is refused',()=>{
 const x=lab();proposal(x);x.run('eclipseV442Approve()');
 assert.equal(x.sent.filter(t=>t[0]==='request').length,0);
 assert.match(x.el('e442Status').textContent,/authorization acknowledgment/);
});
test('Approving with consent forwards exactly once to native approval; never executes directly',()=>{
 const x=lab();proposal(x);x.el('e442Consent').checked=true;
 x.run('eclipseV442Approve()');
 const requests=x.sent.filter(t=>t[0]==='request');assert.equal(requests.length,1);
 assert.equal(requests[0][1],'https://httpbin.org/get');assert.equal(requests[0][2],'httpbin.org');assert.equal(requests[0][3],'HEAD');
 assert.equal(x.el('e44Consent').checked,false);
 assert.match(x.el('e442Thread').innerHTML,/Android approval once/);
});
test('deny never sends request and clears pending card',()=>{
 const x=lab();proposal(x);x.run('eclipseV442Deny()');
 assert.equal(x.sent.filter(t=>t[0]==='request').length,0);
 assert.match(x.el('e442Thread').innerHTML,/discarded that proposal/);
 assert.equal(x.run('eclipseV442Proposal'),null);
});
test('modify path/method needs renewed consent; GET warning; native still validates',()=>{
 const x=lab();proposal(x);x.run('eclipseV442Modify()');
 x.el('e442EditPath').value='/headers';x.el('e442EditMethod').value='GET';
 x.run('eclipseV442SaveModification()');
 assert.equal(x.run('eclipseV442Proposal.path'),'/headers');
 assert.equal(x.run('eclipseV442Proposal.method'),'GET');
 assert.match(x.el('e442Thread').innerHTML,/GET can change server state/);
 x.run('eclipseV442Approve()');assert.equal(x.sent.filter(t=>t[0]==='request').length,0);
 x.el('e442Consent').checked=true;x.run('eclipseV442Approve()');
 assert.deepEqual(x.sent.filter(t=>t[0]==='request').at(-1).slice(1,4),['https://httpbin.org/headers','httpbin.org','GET']);
});
test('modified URL query, encoded traversal, double-slashes never become approved',()=>{
 const x=lab();proposal(x);
 for(const path of ['/admin?u=x','/%2e%2e/x','//host/path','/../foo']){
  x.run('eclipseV442Modify()');x.el('e442EditPath').value=path;x.el('e442EditMethod').value='HEAD';x.run('eclipseV442SaveModification()');
  assert.equal(x.run('eclipseV442Proposal.path'),'/get');
 }
 assert.equal(x.sent.filter(t=>t[0]==='request').length,0);
});
test('changed scope invalidates proposal and blocks submission',()=>{
 const x=lab();proposal(x);x.el('e44Scope').value='elsewhere.org';x.run('eclipseV442InvalidateScope()');x.el('e442Consent').checked=true;x.run('eclipseV442Approve()');
 assert.equal(x.sent.filter(t=>t[0]==='request').length,0);
});
test('scope changes during generation discard stale AI proposal',()=>{
 const x=lab();x.el('e44Scope').value='httpbin.org';x.el('e442Input').value='check';x.run("eclipseV442Send('plan')");
 const id=x.sent.filter(t=>t[0]==='ai').at(-1)[2];x.el('e44Program').value='Policy changed mid-generation';
 x.run(`eclipseV441AiResult(${id},true,"METHOD: HEAD\\nPATH: /")`);
 assert.equal(x.run('eclipseV442Proposal'),null);
});
test('native results and rejection reach chat only for matching request IDs',()=>{
 const x=lab();proposal(x);x.el('e442Consent').checked=true;x.run('eclipseV442Approve()');
 const id=x.sent.filter(t=>t[0]==='request')[0][4];
 x.run(`eclipseV44Result(${id+1},true,"not a response")`);assert.equal(x.run('eclipseV442NativePending'),id);
 x.run(`eclipseV44Result(${id},true,${JSON.stringify(JSON.stringify({environment:'approved_live_https',method:'HEAD',host:'httpbin.org',path:'/get',status:200,sample_bytes:0,note:'metadata'}))})`);
 assert.match(x.el('e442Thread').innerHTML,/HTTP 200/);assert.equal(x.run('eclipseV442NativePending'),0);
 assert.equal(x.run('eclipseV441Evidence.status'),200);
});
test('native rejection does not claim evidence or create automatic follow-up',()=>{
 const x=lab();proposal(x);x.el('e442Consent').checked=true;x.run('eclipseV442Approve()');
 const id=x.sent.filter(t=>t[0]==='request')[0][4];x.run(`eclipseV44Result(${id},false,"Rejected by owner")`);
 assert.match(x.el('e442Thread').innerHTML,/Rejected by owner/);
 assert.equal(x.sent.filter(t=>t[0]==='request').length,1);
});
test('transcript is escaped, bounded and stored locally; clear chat preserves evidence',()=>{
 const x=lab();x.run(`eclipseV442Post('you','<img src=x onerror=alert(1)>')`);
 assert.doesNotMatch(x.el('e442Thread').innerHTML,/<img/);
 assert.match(x.el('e442Thread').innerHTML,/&lt;img/);
 assert.ok(x.store.has('nova.eclipse.v442.chat.v1'));
 x.run('eclipseV442Clear()');assert.equal(x.run('eclipseV442Messages.length'),0);
 assert.equal(x.sent.filter(t=>t[0]==='clear').length,0);
});
test('Eclipse notifications use existing Android channel only when app is backgrounded',()=>{
 assert.match(html,/onclick="eclipseV442EnableAlerts\(\)"/);
 assert.match(html,/function eclipseV442EnableAlerts\(\)/);
 assert.match(java,/ECLIPSE_V442_CHAT_FLOW/);assert.match(html,/Previous conversation \(untrusted\)/);
 assert.match(java,/if\(!novaForeground\)runOnUiThread\(\(\)->copilotNotify\("Eclipse finished thinking"/);
 assert.match(java,/if\(!novaForeground\)runOnUiThread\(\(\)->copilotNotify\("Eclipse needs attention"/);
 assert.match(fs.readFileSync('app/src/main/AndroidManifest.xml','utf8'),/POST_NOTIFICATIONS/);
 assert.match(gradle,/versionCode 8/);
 assert.match(wf,/test-eclipse-v442\.cjs/);
});
