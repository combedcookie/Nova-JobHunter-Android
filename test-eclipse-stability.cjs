// ECLIPSE_STABILITY_V43: offline and approval-gated regression tests.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('app/src/main/assets/index.html','utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
assert.ok(scripts.some(s=>s.includes('ECLIPSE_STABILITY_V43')));
function make(state={}) {
 const elements={};
 const calls=[];
 const store=new Map(Object.entries(state));
 const el=id=>elements[id]||=( {
   value:'',textContent:'',innerHTML:'',checked:false,
   classList:{toggle(){},remove(){}},setAttribute(){},focus(){},
   replaceChildren(){this.innerHTML='';},append(){},scrollIntoView(){}
 } );
 const bridge={
   novaLabRequest(...args){calls.push(['lab',...args])},
   novaH1Details(){},searchProvider(){},listProfiles(){},
   open(){},saveProfile(){},novaGenerate(){},
 };
 const document={getElementById:el,querySelectorAll(){return []},body:{setAttribute(){}},createElement(){return {className:'',textContent:'',href:'',target:'',rel:'',append(){}}}};
 const ctx=vm.createContext({document,window:{Nova:bridge,addEventListener(){}},Nova:bridge,
   localStorage:{getItem:k=>store.get(k)||null,setItem(k,v){store.set(k,v)}},
   console,Date,JSON,URL,Number,Math,Set,Map,Promise,
   alert(){},confirm(){return true},prompt(){return null},
   setTimeout(){return 0},clearTimeout(){},encodeURIComponent,decodeURIComponent});
 for(const s of scripts)vm.runInContext(s,ctx);
 return {elements,el,store,calls,run:src=>vm.runInContext(src,ctx)};
}
test('one visible knowledge panel, without redundant V4.1 panel',()=>{
 const a=make();a.run("show('Security Lab')");
 const markup=a.el('content').innerHTML;
 assert.equal((markup.match(/Eclipse · Security Knowledge/g)||[]).length,1);
 assert.doesNotMatch(markup,/Eclipse · Offline knowledge core/);
});
test('knowledge notebook hydrates when navigating directly to Security Lab',()=>{
 const text='RESEARCH PLAN: local evidence only';
 const a=make({'nova.manager.notebook.v1':text});
 a.run("show('Security Lab')");
 assert.equal(a.el('eclipseNotebookTextV42').textContent,text);
});
test('stop during pending Android request keeps the result from scheduling another',()=>{
 const a=make();a.run('eclipseV4Resume()');a.run('eclipseLoopApprove()');
 assert.equal(a.calls.length,1);
 a.run('eclipseV4Stop()');
 assert.match(a.run('eclipseLoopRead().status'),/in-flight/);
 a.run("novaLabResult("+a.calls[0][3]+",true,"+JSON.stringify(JSON.stringify({environment:'offline_mock',request:'GET /api/orders/demo-101',account:'A',status:200,approved_once:true,network_used:false}))+")");
 assert.equal(a.run('eclipseLoopRead().paused'),true);
 assert.equal(a.run('eclipseLoopRead().pending'),null);
 assert.equal(a.run('eclipseV4Covered(eclipseLoopRead()).size'),1);
});
test('resume cannot override an in-progress native approval',()=>{
 const a=make();a.run('eclipseV4Resume()');a.run('eclipseLoopApprove()');
 a.run('eclipseV4Stop()');a.run('eclipseV4Resume()');
 assert.equal(a.run('eclipseLoopRead().paused'),true);
 assert.equal(a.calls.length,1);
});
test('manual lab cannot race automatic request',()=>{
 const a=make();a.run('eclipseV4Resume()');a.run('eclipseLoopApprove()');
 a.el('novaLabAccount').value='A';a.el('novaLabPath').value='/api/users';
 a.el('novaLabOutput').textContent='';a.run('novaLabExecute()');
 assert.equal(a.calls.length,1);
 assert.match(a.el('novaLabOutput').textContent,/Another mock request/);
});
test('rejected native approval pauses investigation without increasing coverage',()=>{
 const a=make();a.run('eclipseV4Resume()');a.run('eclipseLoopApprove()');
 a.run('novaLabResult('+a.calls[0][3]+',false,"Rejected by user")');
 assert.equal(a.run('eclipseV4Covered(eclipseLoopRead()).size'),0);
 assert.equal(a.run('eclipseLoopRead().paused'),true);
 assert.equal(a.run('eclipseLoopRead().pending'),null);
});
test('process restart recovers stale persisted approval safely',()=>{
 const initial=JSON.stringify({active:{account:'A',path:'/api/users/A'},pending:null,paused:false,history:[]});
 const a=make({'nova.eclipse.loop.v1':initial});
 assert.equal(a.run('eclipseLoopRead().active'),null);
 assert.equal(a.run('eclipseLoopRead().paused'),true);
 assert.match(a.run('eclipseLoopRead().status'),/interrupted/);
});
test('missing local knowledge has no external network dependency',()=>{
 const a=make();
 assert.ok(a.run("eclipseKnowledgeSearchV41('CWE-639',8).some(x=>x.id==='CWE-639')"));
 assert.ok(a.run("eclipseKnowledgeSearchV41('authentication',8).length")>0);
 assert.equal(a.calls.length,0);
});
test('10 unique approved mock results complete coverage and stop queueing',()=>{
 const a=make();
 a.run("eclipseLoopSave({history:eclipseV4Plan.map(v=>({account:v[0],path:v[1],ok:true,status:eclipseV4Expected(v[0],v[1]),expected:eclipseV4Expected(v[0],v[1])})),paused:false,pending:null,active:null})");
 a.run('eclipseV4Queue(eclipseLoopRead())');
 assert.equal(a.run('eclipseV4Next(eclipseLoopRead())'),undefined);
 assert.equal(a.run('eclipseV4Covered(eclipseLoopRead()).size'),10);
});
test('Security Lab shares a bounded evidence summary with NOVA context',()=>{
 const a=make();a.run("show('Security Lab')");
 assert.match(a.run('novaScreenContext()'),/Eclipse offline evidence/);
});
test('legacy NOVA mock dispatch respects an active Eclipse request',()=>{
 const a=make();a.run('eclipseV4Resume()');a.run('eclipseLoopApprove()');
 assert.equal(a.calls.length,1);
 a.run("novaUnifiedPending='mock';novaUnifiedApprove()");
 assert.equal(a.calls.length,1);
 assert.match(a.run('novaUnifiedResult'),/Finish the current mock request/);
});
test('Java bridge profiles require validated identifiers',()=>{
 const java=fs.readFileSync('app/src/main/java/com/nova/jobhunter/MainActivity.java','utf8');
 assert.match(java,/activateProfile\(String provider,String name,int id\).*?provider==null/);
 assert.match(java,/deleteProfile\(String provider,String name,int id\).*?provider==null/);
 assert.match(java,/setOnApplyWindowInsetsListener/);
});
