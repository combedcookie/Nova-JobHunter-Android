
/* Hermes V5 consolidated marketplace. All user data remains on device. */
(function(){
'use strict';
const K='nova.hermes.v5';
function read(){try{return JSON.parse(localStorage.getItem(K))||{}}catch(e){return {}}}
let state=Object.assign({query:'help desk',location:'Newark, OH',radius:50,local:true,remote:true,relocate:false,minPay:0,minimumScore:25,tab:'discover',items:[],selected:[],approved:[],batch:null,round:0,notice:'Ready.',busy:false},read());
state.busy=false;
if(!Array.isArray(state.items))state.items=[];
if(!Array.isArray(state.selected))state.selected=[];
if(!Array.isArray(state.approved))state.approved=[];
let diagnostics=[];
const save=()=>{try{localStorage.setItem(K,JSON.stringify(state))}catch(e){state.notice='Storage full; changes not saved.'}};
const html=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const val=id=>document.getElementById(id)?.value||'';
const check=id=>!!document.getElementById(id)?.checked;
const uniq=j=>String(j.url||'').split('#')[0].replace(/\/$/,'').toLowerCase();
/* HERMES_V52_DISCOVERY: broaden searches without claiming additional providers. */
const keywords=['help desk','IT support','desktop support','service desk','technical support','IT technician','computer technician','application support','junior QA','software tester','junior developer','technical analyst'];
function score(j){
 let n=20;const t=(j.title+' '+j.description).toLowerCase();
 for(const word of ['help desk','it support','desktop support','technical support','troubleshoot','windows','linux','python','android','qa','junior','entry','software','network'])if(t.includes(word))n+=5;
 return Math.min(n,95);
}
function render(){
 const total=state.items.length,sel=state.selected.length,ap=state.approved.length;
 let h=`<section class="obs-hero"><div class="obs-kicker">CAREER INTELLIGENCE · HERMES V5</div><h1>▣ JOBHUNTER</h1><p>Your personal job marketplace</p><div class="obs-stats"><div><b>${total}</b><small>DISCOVERED</small></div><div><b>${sel}</b><small>SELECTED</small></div><div><b>${ap}</b><small>APPROVED</small></div></div></section>`;
 h+=`<div style="display:flex;gap:8px;flex-wrap:wrap;margin:10px 0"><button class="action secondary" onclick="show('Settings')">⚙ App settings / API keys</button><button class="action secondary" onclick="show('Autopilot')">Resume profile</button></div>`;
 h+=`<div class="obs-links"><button class="action ${state.tab==='discover'?'':'secondary'}" onclick="hermesV5Tab('discover')">Discover</button><button class="action ${state.tab==='autoapply'?'':'secondary'}" onclick="hermesV5Tab('autoapply')">AutoApply</button><button class="action ${state.tab==='applications'?'':'secondary'}" onclick="hermesV5Tab('applications')">My Applications</button></div>`;
 if(state.tab==='discover'){
 h+=`<div class="item"><h2>Search jobs</h2><label>Role or keyword</label><input id="hvQuery" value="${html(state.query)}" placeholder="Help desk"><label>Home location</label><input id="hvLocation" value="${html(state.location)}"><div class="autopilot-grid"><div><label>Commute radius (miles)</label><select id="hvRadius">${[25,50,75,100].map(n=>`<option value="${n}" ${state.radius===n?'selected':''}>${n} miles</option>`).join('')}</select></div><div><label>Minimum listed annual pay</label><select id="hvPay">${[0,40000,60000,75000,90000].map(n=>`<option value="${n}" ${state.minPay===n?'selected':''}>${n?'$'+n.toLocaleString():'Any / undisclosed'}</option>`).join('')}</select></div></div><label><input type="checkbox" id="hvLocal" style="width:auto" ${state.local?'checked':''}> Local jobs</label><label><input type="checkbox" id="hvRemote" style="width:auto" ${state.remote?'checked':''}> Remote jobs</label><label><input type="checkbox" id="hvRelocate" style="width:auto" ${state.relocate?'checked':''}> Open to relocation (nationwide discovery)</label><p class="note">Location and pay are advisory filters when a source lacks structured data. Unknown salary is never treated as meeting a minimum.</p><button class="action" onclick="hermesV5Search(false)" ${state.busy?'disabled':''}>Search all configured sources</button><button class="action secondary" onclick="hermesV5Search(true)" ${state.busy?'disabled':''}>Load more job matches</button></div>`;
 const visible=state.items.filter(j=>{if(state.minPay&&(!j.pay||j.pay<state.minPay))return false;if(!state.relocate&&!j.remote&&!state.local)return false;if(!state.remote&&j.remote)return false;return true}).sort((a,b)=>b.score-a.score);
 h+=`<p class="note">${html(state.notice)} · ${visible.length} displayed / ${total} saved · Searches cover Remotive, Adzuna and USAJOBS only. Local distance is not verified without geocoding.</p>`;
 h+=visible.slice(0,250).map(j=>`<div class="item"><div class="name">${html(j.title)}</div><div class="meta">${html(j.company)} · ${html(j.location)} · ${html(j.provider)} · ${j.score}% heuristic match</div><p class="note">${html(j.remote?'Remote listed':'Location must be verified')}${j.pay?' · Listed pay from $'+j.pay.toLocaleString():''}</p><label><input type="checkbox" style="width:auto" onchange="hermesV5Select('${j.id}',this.checked)" ${state.selected.includes(j.id)?'checked':''}> Select for application</label><button class="action secondary" onclick="hermesV5Open('${j.id}')">Open original posting</button></div>`).join('')||'<div class="empty">No matching jobs yet. Search to begin.</div>';
 }else if(state.tab==='autoapply'){
 h+=`<div class="item"><h2>Resume intelligence</h2><p class="note">Tailoring uses only your saved verified profile and imported resume. No credentials, dates, or degrees will be invented.</p><button class="action secondary" onclick="show('Autopilot')">Import or edit verified resume</button><p class="note">${html((window.apProfile?.experience||'').slice(0,180))||'Save your verified experience in Autopilot before generating drafts.'}</p></div>`;
 h+=`<div class="item"><h2>Approved batch workflow</h2><p class="note">Choose jobs in Discover. Review truthful documents per job. Approved batches authorize submission only on future supported automated connectors; current employer forms require your manual action. Never claim submission without confirmation.</p><div>${sel} jobs selected · ${ap} approved</div><button class="action" onclick="hermesV5ApproveBatch()">Review and approve selected batch</button></div>`;
 h+=state.items.filter(j=>state.selected.includes(j.id)).map(j=>`<div class="item"><div class="name">${html(j.title)} · ${html(j.company)}</div><div class="meta">${html(j.status||'Selected')} ${state.approved.includes(j.id)?'· Batch approved':''}</div><button class="action secondary" onclick="hermesV5Draft('${j.id}')">Tailored resume + letter</button><button class="action secondary" onclick="hermesV5Open('${j.id}')">Open application</button></div>`).join('');
 }else{
 h+=`<h2>Application ledger</h2><p class="note">Submitted requires user-entered confirmation evidence. Opening an external link never counts as submission.</p>`;
 h+=state.items.filter(j=>state.selected.includes(j.id)||j.status).map(j=>`<div class="item"><div class="name">${html(j.title)} · ${html(j.company)}</div><div class="meta">${html(j.status||'Selected')} · ${html(j.confirmation||'No submission evidence')}</div><button class="action secondary" onclick="hermesV5Open('${j.id}')">Open application</button>${state.approved.includes(j.id)?`<button class="action" onclick="hermesV5Record('${j.id}')">Record confirmation</button>`:''}</div>`).join('')||'<div class="empty">No applications tracked.</div>';
 }
 return h;
}
const oldShow=window.show;
window.show=function(t){if(['Hermes','Hermes Scout'].includes(t)){state.tab=t==='Hermes Scout'?'discover':state.tab;const n=document.getElementById('nav');if(n)n.classList.remove('open');window.tab='Hermes';if(typeof window.nav==='function')window.nav();document.getElementById('content').innerHTML=render();document.body?.setAttribute('data-obsidian-page','Hermes');return}return oldShow.apply(this,arguments)};
window.hermesV5Tab=t=>{state.tab=t;save();show('Hermes')};
window.hermesV5Select=(id,checked)=>{state.selected=state.selected.filter(x=>x!==id);if(checked)state.selected.push(id);save()};
/* V5.2 keeps external applications user-controlled until a tested site-specific browser runner exists. */
window.hermesV5Open=id=>{const j=state.items.find(x=>x.id===id);if(j&&/^https:\/\//.test(j.url)&&window.Nova?.open)Nova.open(j.url)};
window.hermesV5Draft=id=>{
 const j=state.items.find(x=>x.id===id);if(!j)return;
 const p=typeof apProfile!=='undefined'?apProfile:{},experience=String(p.experience||'').trim();
 if(!experience){alert('First save verified experience in Autopilot.');return}
 const terms=experience.split(/[.\n;]/).map(x=>x.trim()).filter(Boolean).slice(0,30);
 const jd=(j.title+' '+j.description).toLowerCase();
 const ranked=terms.map(t=>({t,n:t.toLowerCase().split(/\W+/).filter(w=>w.length>3&&jd.includes(w)).length})).sort((a,b)=>b.n-a.n);
 const facts=ranked.slice(0,10).map(x=>'- '+x.t).join('\n');
 const resume='TAILORED RESUME DRAFT — VERIFY BEFORE SUBMISSION\n'+(p.name||'[Name]')+'\n'+(p.contact||'[Contact]')+'\nTarget: '+j.title+' · '+j.company+'\n\nVERIFIED RELEVANT EXPERIENCE\n'+facts+'\n\nNo facts have been added beyond your saved profile.';
 const letter='COVER LETTER DRAFT — REVIEW\n\nDear Hiring Team,\nI am applying for '+j.title+' at '+j.company+'. My relevant experience includes:\n'+facts+'\n\nI would welcome the opportunity to discuss this role.\nSincerely,\n'+(p.name||'[Name]');
 const combined=resume+'\n\n-------------------\n\n'+letter;
 if(navigator.clipboard?.writeText)navigator.clipboard.writeText(combined).then(()=>alert('Tailored resume and cover letter copied. Review before use.')).catch(()=>prompt('Copy draft:',combined));
 else prompt('Copy draft:',combined);
};
window.hermesV5ApproveBatch=()=>{
 const pending=state.selected.filter(id=>!state.approved.includes(id));
 if(!pending.length){alert('Select new jobs in Discover first.');return}
 if(!(typeof apProfile!=='undefined'&&apProfile.experience&&apProfile.experience.trim())){alert('Save verified experience in Autopilot first.');return}
 const preview=pending.map(id=>state.items.find(j=>j.id===id)).filter(Boolean).map(j=>j.company+' — '+j.title).join('\n');
 if(!confirm('Approve this batch of '+pending.length+' applications for preparation?\n\n'+preview.slice(0,1800)+'\n\nThis does NOT automatically submit to employer sites.'))return;
 state.approved.push(...pending);state.batch={approvedAt:new Date().toISOString(),ids:pending};for(const j of state.items)if(pending.includes(j.id))j.status='Approved — awaiting external submission';save();state.tab='applications';show('Hermes');
};
window.hermesV5Record=id=>{
 const j=state.items.find(x=>x.id===id);if(!j||!state.approved.includes(id))return;
 const evidence=prompt('Enter the employer confirmation ID, confirmation email subject, or other evidence. Cancel if not submitted:');
 if(!evidence||!evidence.trim()){alert('No confirmation recorded. Application remains awaiting submission.');return}
 j.status='Submitted — user confirmed';j.confirmation=evidence.trim().slice(0,300);j.submittedAt=new Date().toISOString();save();show('Hermes');
};
let tasks=[],active=null,requestId=950000;
const priorResult=window.novaProviderResult;
window.novaProviderResult=function(id,ok,payload){
 if(!active||id!==active.id)return priorResult.apply(this,arguments);
 const current=active;active=null;
 try{
  if(!ok)throw Error(String(payload||'Provider request failed'));
  const data=JSON.parse(payload);
  let results=[];
  if(current.provider==='remotive')results=(data.jobs||[]).map(j=>({title:j.title,company:j.company_name,location:j.candidate_required_location||'Remote',description:String(j.description||'').replace(/<[^>]*>/g,' ').slice(0,1200),url:j.url,remote:true,pay:0}));
  if(current.provider==='adzuna')results=(data.results||[]).map(j=>({title:j.title,company:j.company?.display_name,location:j.location?.display_name,description:String(j.description||'').replace(/<[^>]*>/g,' ').slice(0,1200),url:j.redirect_url,remote:/remote/i.test(j.title+' '+j.description),pay:Number(j.salary_min)||0}));
  if(current.provider==='usajobs')results=(data.SearchResult?.SearchResultItems||[]).map(x=>{const j=x.MatchedObjectDescriptor||{};return {title:j.PositionTitle,company:j.OrganizationName,location:j.PositionLocationDisplay,description:String(j.UserArea?.Details?.JobSummary||'').replace(/<[^>]*>/g,' ').slice(0,1200),url:j.PositionURI,remote:/remote/i.test(j.PositionLocationDisplay||''),pay:0}});
  let added=0;
  for(const j of results){
   if(!/^https:\/\//.test(j.url||''))continue;
   const key=uniq(j);if(state.items.some(x=>x.key===key))continue;
   const s=score(j);if(s<state.minimumScore)continue;
   const id='h'+(++requestId);
   state.items.push(Object.assign({id,key,provider:current.provider,score:s},j));added++;
  }
  diagnostics.push(current.provider+' / '+current.query+': '+results.length+' returned, '+added+' new');state.notice=diagnostics.slice(-5).join(' | ');
 }catch(e){diagnostics.push(current.provider+' / '+current.query+': '+String(e.message).slice(0,95));state.notice=diagnostics.slice(-5).join(' | ')}
 save();next();
};
function next(){
 if(!tasks.length){state.busy=false;state.notice=(diagnostics.join('\n')||'No provider responses')+'\nSearch complete. '+state.items.length+' total saved. Provider APIs may be limited.';save();show('Hermes');return}
 const task=tasks.shift();active={...task,id:++requestId};
 state.notice='Searching '+task.provider+' ('+(tasks.length+1)+' remaining)…';show('Hermes');
 try{Nova.searchProvider(task.provider,task.query,task.location,active.id)}catch(e){active=null;state.notice='Request failed: '+e.message;next()}
}
window.hermesV5Search=more=>{
 if(state.busy)return;
 state.query=val('hvQuery').trim().slice(0,100)||'help desk';state.location=val('hvLocation').trim().slice(0,100)||'Newark, OH';
 state.radius=Number(val('hvRadius'))||50;state.minPay=Number(val('hvPay'))||0;
 state.local=check('hvLocal');state.remote=check('hvRemote');state.relocate=check('hvRelocate');
 if(!state.local&&!state.remote&&!state.relocate){alert('Enable at least one search area.');return}
 if(!window.Nova?.searchProvider){state.notice='Install the Android app to search live jobs.';show('Hermes');return}
 const offset=more?(state.round++ * 3 + 3):0;
 const terms=more?keywords.slice(offset,offset+3):[state.query,...keywords.filter(k=>k.toLowerCase()!==state.query.toLowerCase()).slice(0,2)];
 if(!terms.length){state.notice='All '+keywords.length+' suggested role searches completed. Try a different keyword or location.';show('Hermes');return;}
 if(!more){state.round=0;state.notice='Starting search…'} diagnostics=[];
 tasks=[];
 for(const term of terms){
  if(state.remote)tasks.push({provider:'remotive',query:term,location:''});
  if(state.local||state.relocate){
   tasks.push({provider:'adzuna',query:term,location:state.relocate?'United States':state.location});
   tasks.push({provider:'usajobs',query:term,location:state.relocate?'United States':state.location});
  }
 }
 state.busy=true;save();next();
};
})();
