/* NOVA global settings V5.1: app-wide appearance, no credential changes. */
(function(){
'use strict';
const KEY='nova.appearance.v1';
let theme={color:'#36b6c5',strength:55};
try{theme=Object.assign(theme,JSON.parse(localStorage.getItem(KEY)||'{}'))}catch(e){}
function safeColor(c){return /^#[0-9a-fA-F]{6}$/.test(c||'')?c:'#36b6c5'}
function hexRgb(h){return [1,3,5].map(i=>parseInt(h.slice(i,i+2),16))}
function blend(a,b,t){return '#'+a.map((n,i)=>Math.round(n*(1-t)+b[i]*t).toString(16).padStart(2,'0')).join('')}
function apply(){
 theme.color=safeColor(theme.color);theme.strength=Math.min(100,Math.max(0,Number(theme.strength)||0));
 const rgb=hexRgb(theme.color),light=blend(rgb,[255,255,255],.32),dark=blend(rgb,[4,17,30],.58);
 const style=document.getElementById('nova-v51-theme')||document.createElement('style');style.id='nova-v51-theme';
 style.textContent=`:root{--nova-user-accent:${theme.color};--nova-user-light:${light};--nova-user-dark:${dark};--copper:${theme.color};--neon:${theme.color};--nova-cyan:${theme.color};--hq-accent:${theme.color}}
 .star,.nova-eyebrow,.obs-kicker{color:${light}!important}
 #content .action:not(.secondary),#content button.action:not(.secondary){background:linear-gradient(115deg,${theme.color},${dark})!important;border-color:${theme.color}!important;color:#fff!important}
 #content .action.secondary{border-color:${theme.color}!important}
 .nova-bottom-nav button.active{border-color:${theme.color}!important;color:${light}!important;box-shadow:0 0 ${Math.round(theme.strength/6)}px ${theme.color}55!important;animation:none!important}
 input:focus,textarea:focus,select:focus{outline-color:${theme.color}!important}
 #content .item:focus-within{border-color:${theme.color}!important}
 #nova-global-settings{border:1px solid ${theme.color}!important;color:${light}!important}
 #content .obs-links button{border-color:${theme.color}!important}
 #content .obs-links button:first-child{background:linear-gradient(115deg,${dark},${theme.color})!important}
 .nova-v51-swatch{height:55px;border-radius:12px;background:linear-gradient(110deg,${dark},${theme.color},${light});border:1px solid ${theme.color};margin:10px 0}`;
 document.head.appendChild(style);
}
function installGear(){
 const header=document.querySelector('header.top')||document.querySelector('.top');if(!header||document.getElementById('nova-global-settings'))return;
 const b=document.createElement('button');b.type='button';b.id='nova-global-settings';b.textContent='⚙';b.title='App settings';b.setAttribute('aria-label','App settings');b.style.cssText='flex:0 0 auto;border-radius:11px;background:#14212e;font-size:25px;padding:6px 12px;min-width:48px;min-height:48px;cursor:pointer;';
 b.addEventListener('click',()=>window.show('Settings'));header.appendChild(b);
}
function addAppearance(){
 const content=document.getElementById('content');if(!content||document.getElementById('nova-v51-appearance'))return;
 const wrap=document.createElement('section');wrap.id='nova-v51-appearance';wrap.className='item';
 wrap.innerHTML='<h2>App appearance</h2><p class="note">Theme applies to NOVA Board, Hermes, and Eclipse. Settings are saved locally on this device.</p><label for="nova-v51-color">Accent color wheel</label><input type="color" id="nova-v51-color" style="height:64px;width:100%;padding:5px;cursor:pointer"><label for="nova-v51-glow">Gradient glow intensity</label><input type="range" id="nova-v51-glow" min="0" max="100" step="5"><div class="nova-v51-swatch"></div><button class="action secondary" type="button" id="nova-v51-reset">Reset default theme</button><h2>API credentials</h2><p class="note">Existing encrypted Adzuna, USAJOBS and HackerOne profiles remain in the API key manager below. Use Refresh profiles to check saved profiles; keys are not displayed.</p>';
 content.insertBefore(wrap,content.firstChild);
 const picker=wrap.querySelector('#nova-v51-color'),glow=wrap.querySelector('#nova-v51-glow');picker.value=safeColor(theme.color);glow.value=String(theme.strength);
 picker.addEventListener('input',()=>{theme.color=picker.value;apply();try{localStorage.setItem(KEY,JSON.stringify(theme))}catch(e){}});
 glow.addEventListener('input',()=>{theme.strength=Number(glow.value);apply();try{localStorage.setItem(KEY,JSON.stringify(theme))}catch(e){}});
 wrap.querySelector('#nova-v51-reset').addEventListener('click',()=>{theme={color:'#36b6c5',strength:55};picker.value=theme.color;glow.value=String(theme.strength);apply();try{localStorage.setItem(KEY,JSON.stringify(theme))}catch(e){}});
}
const oldShow=window.show;
window.show=function(t){const result=oldShow.apply(this,arguments);installGear();if(t==='Settings')addAppearance();return result};
apply();installGear();
})();
