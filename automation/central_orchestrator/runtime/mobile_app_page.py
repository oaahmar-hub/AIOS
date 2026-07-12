#!/usr/bin/env python3
"""The AIOS mobile command app - one phone-first page served at /app.

Vanilla HTML/JS (no CDN, no build step) calling the runtime's own APIs
same-origin, so the browser's basic-auth session covers everything.
Add-to-Home-Screen turns it into Omar's app icon.
"""

APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>AIOS</title>
<style>
:root{--bg:#0b1220;--card:#121a2c;--line:#22304d;--txt:#e8eefc;--dim:#8fa3c8;--acc:#4fd1c5;--warn:#f6ad55;--bad:#fc8181;--ok:#68d391}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
body{background:var(--bg);color:var(--txt);font:16px/1.45 -apple-system,system-ui,sans-serif;padding-bottom:84px}
header{padding:18px 16px 10px}h1{font-size:22px}h1 span{color:var(--acc)}
#status{font-size:13px;color:var(--dim);margin-top:2px}
.tabs{position:fixed;bottom:0;left:0;right:0;display:flex;background:#0e1626;border-top:1px solid var(--line);padding-bottom:env(safe-area-inset-bottom)}
.tabs button{flex:1;background:none;border:0;color:var(--dim);font-size:11px;padding:10px 2px 12px;cursor:pointer}
.tabs button.on{color:var(--acc)}.tabs .ico{display:block;font-size:20px;margin-bottom:2px}
main{padding:8px 14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px;margin:10px 0}
.row{display:flex;gap:8px;margin:10px 0}
input,select{flex:1;background:#0e1626;border:1px solid var(--line);border-radius:10px;color:var(--txt);padding:12px;font-size:16px}
.btn{background:var(--acc);color:#04222b;border:0;border-radius:10px;padding:12px 16px;font-weight:700;font-size:15px;cursor:pointer}
.btn:disabled{opacity:.5}
.item{border-bottom:1px solid var(--line);padding:10px 0;font-size:14px}
.item:last-child{border-bottom:0}
.item b{display:block;font-size:15px}
.dim{color:var(--dim);font-size:12.5px}
.pill{display:inline-block;border-radius:20px;padding:2px 10px;font-size:12px;font-weight:700;margin:2px 4px 2px 0}
.ok{background:#123c2a;color:var(--ok)}.bad{background:#43181c;color:var(--bad)}.na{background:#243048;color:var(--dim)}
.warnbox{background:#3a2b12;color:var(--warn);border-radius:8px;padding:6px 10px;font-size:12.5px;margin-top:6px}
pre{white-space:pre-wrap;font-size:13px;color:var(--txt)}
.hide{display:none}
a{color:var(--acc)}
.loading{color:var(--dim);padding:14px;text-align:center}
</style>
</head>
<body>
<header><h1>AIOS <span>·</span> Command</h1><div id="status">checking system…</div></header>
<main>
<!-- UNITS -->
<section id="tab-units">
  <div class="card"><div class="row">
    <input id="uq" placeholder="e.g. 1BR JVC under 900k / verdana / palm villa" enterkeyhint="search">
    <button class="btn" onclick="findUnits()">Find</button></div>
    <div class="dim">Searches your 2,900+ verified units only — never portal guesses.</div>
  </div>
  <div class="card" id="ur"><div class="loading">Search your real inventory ↑</div></div>
</section>
<!-- OWNERS -->
<section id="tab-owners" class="hide">
  <div class="card"><div class="row">
    <input id="oq" placeholder="building name · permit # · or paste a Bayut/PF/Dubizzle link" enterkeyhint="search">
    <button class="btn" onclick="findOwners()">Owners</button></div>
    <div class="dim">Real DLD owners across 46 Dubai areas (370k+ phones). Mobiles masked — tap to reveal with your admin key.</div>
  </div>
  <div class="card" id="or"><div class="loading">Search building / permit / paste a link ↑</div></div>
</section>
<!-- LEADS -->
<section id="tab-leads" class="hide">
  <div class="card"><button class="btn" onclick="loadLeads()">Refresh leads</button></div>
  <div class="card" id="lr"><div class="loading">Tap refresh to load group leads</div></div>
</section>
<!-- CHECK (engineering) -->
<section id="tab-eng" class="hide">
  <div class="card">
    <div class="row"><input id="eplot" placeholder="Plot area m²" inputmode="decimal"><input id="egfa" placeholder="GFA m²" inputmode="decimal"></div>
    <div class="row"><input id="efloors" placeholder="Floors e.g. B+G+2"><button class="btn" onclick="checkDesign()">Check</button></div>
    <div class="dim">Audits vs verified Nakheel DCR (Palm Jumeirah villa rules).</div>
  </div>
  <div class="card" id="er"><div class="loading">Enter a design to audit ↑</div></div>
</section>
<!-- MARKET -->
<section id="tab-market" class="hide">
  <div class="card" id="mkt"><div class="loading">Loading live market…</div></div>
  <div class="card"><div class="row">
    <input id="lq" placeholder="paste a Bayut/PF link → asking vs market" enterkeyhint="go">
    <button class="btn" onclick="assessListing()">Check</button></div>
    <div class="dim">Official DLD sale index + listing price check.</div>
  </div>
  <div class="card hide" id="lr2"></div>
</section>
<!-- RENEWALS -->
<section id="tab-renew" class="hide">
  <div class="card"><div class="row">
    <select id="rd"><option value="30">next 30 days</option><option value="60" selected>next 60 days</option><option value="90">next 90 days</option></select>
    <button class="btn" onclick="loadRenewals()">Find</button></div>
    <div class="dim">Tenancies expiring soon → owner + re-let pitch. (Needs DLD Ejari data.)</div>
  </div>
  <div class="card" id="rr"><div class="loading">Tap Find ↑</div></div>
</section>
<!-- HEALTH -->
<section id="tab-health" class="hide">
  <div class="card"><button class="btn" onclick="loadHealth()">Refresh health</button></div>
  <div class="card" id="hr"><div class="loading">Tap refresh</div></div>
</section>
</main>
<nav class="tabs">
  <button id="tb-units" class="on" onclick="show('units')"><span class="ico">🔍</span>Units</button>
  <button id="tb-owners" onclick="show('owners')"><span class="ico">✉️</span>Owners</button>
  <button id="tb-market" onclick="show('market')"><span class="ico">📈</span>Market</button>
  <button id="tb-renew" onclick="show('renew')"><span class="ico">🔁</span>Renewals</button>
  <button id="tb-leads" onclick="show('leads')"><span class="ico">🎯</span>Leads</button>
  <button id="tb-eng" onclick="show('eng')"><span class="ico">🏗️</span>Check</button>
  <button id="tb-health" onclick="show('health')"><span class="ico">❤️</span>Health</button>
</nav>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function show(t){for(const x of ['units','owners','market','renew','leads','eng','health']){$('tab-'+x).classList.toggle('hide',x!==t);$('tb-'+x).classList.toggle('on',x===t);}if(t==='market')loadMarket();}
async function api(p){const r=await fetch(p,{headers:{'Accept':'application/json'}});if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}
async function loadMarket(){if($('mkt').dataset.done)return;
 try{const d=await api('/api/market');
  $('mkt').innerHTML=`<div class="item"><b>📈 ${esc(d.brief||'market')}</b>
   <div class="dim">avg flat AED ${d.flat_avg_price?d.flat_avg_price.toLocaleString():'—'} · avg villa AED ${d.villa_avg_price?d.villa_avg_price.toLocaleString():'—'} · ${esc(d.direction||'')}</div>
   <div class="dim">source: ${esc(d.source||'DLD')}</div></div>`;$('mkt').dataset.done=1;
 }catch(e){$('mkt').innerHTML='<div class="item">market data unavailable</div>';}}
async function assessListing(){const u=$('lq').value.trim();if(!u)return;$('lr2').classList.remove('hide');$('lr2').innerHTML='<div class="loading">reading listing…</div>';
 try{const d=await api('/api/listing/assess?url='+encodeURIComponent(u));
  if(!d.asking_price){$('lr2').innerHTML='<div class="item">'+esc(d.note||'could not read the asking price')+'</div>';return;}
  const v=d.verdict?`<span class="pill ${d.verdict.includes('above')?'bad':(d.verdict.includes('below')?'ok':'na')}">${esc(d.verdict)}</span>`:'';
  $('lr2').innerHTML=`<div class="item"><b>${esc(d.building||d.area)} — AED ${Number(d.asking_price).toLocaleString()}</b> ${v}
   <div class="dim">${esc(d.area)} · ${esc(d.portal)} ${d.vs_market_flat_pct!=null?('· '+d.vs_market_flat_pct+'% vs city avg flat'):''}</div></div>`;
 }catch(e){$('lr2').innerHTML='<div class="item">error: '+esc(e.message)+'</div>';}}
async function loadRenewals(){const days=$('rd').value;$('rr').innerHTML='<div class="loading">finding expiring tenancies…</div>';
 try{const d=await api('/api/renewals?days='+days+adminKey());
  if(!d.leads||!d.leads.length){$('rr').innerHTML='<div class="item">No expiring tenancies on file yet. (Needs the DLD Ejari feed — request in progress.)</div>';return;}
  $('rr').innerHTML=d.leads.map(l=>`<div class="item"><b>${esc(l.building||l.area)} ${l.unit?('· '+esc(l.unit)):''}</b>
   <span class="dim">ends ${esc(l.end_date)}${l.owner&&l.owner.phone?(' · owner '+esc(l.owner.name||'')+' '+esc(l.owner.phone)):''}</span>
   <div class="dim">${esc(l.draft||'')}</div></div>`).join('');
 }catch(e){$('rr').innerHTML='<div class="item">error: '+esc(e.message)+'</div>';}}
async function boot(){try{const h=await api('/api/health/deep');$('status').textContent=h.status==='healthy'?'all departments green ✅':'status: '+h.status+' ⚠️';}catch(e){$('status').textContent='cannot reach system';}}
async function findUnits(){const q=$('uq').value.trim();if(!q)return;$('ur').innerHTML='<div class="loading">searching…</div>';
 try{const d=await api('/api/units/search?q='+encodeURIComponent(q));
  if(!d.results||!d.results.length){$('ur').innerHTML='<div class="item">Nothing verified matches. The system never guesses — try another area/project.</div>';return;}
  $('ur').innerHTML=d.results.map(r=>`<div class="item"><b>${esc(r.building||r.project||r.area)}</b>
   <span class="dim">${esc([r.area,r.unit&&('unit '+r.unit),r.bedrooms&&(r.bedrooms+'BR'),r.size,r.price].filter(Boolean).join(' · '))}</span>
   <div class="dim">src: ${esc(r.source||'')}</div></div>`).join('');
 }catch(e){$('ur').innerHTML='<div class="item">error: '+esc(e.message)+'</div>';}}
function adminKey(){let k=localStorage.getItem('aios_admin_key')||'';return k?('&admin_secret='+encodeURIComponent(k)):'';}
function setAdminKey(){const k=prompt('Enter your AIOS admin secret to reveal real owner phone numbers:');if(k){localStorage.setItem('aios_admin_key',k.trim());findOwners();}}
async function findOwners(){const q=$('oq').value.trim();if(!q)return;$('or').innerHTML='<div class="loading">searching real DLD owners…</div>';
 try{
  // A pasted Bayut/PF/Dubizzle link -> owner via the listing; else building/unit search.
  const isUrl=/^https?:\/\//i.test(q);
  const url=isUrl?('/api/owner/from-url?url='+encodeURIComponent(q)+adminKey())
                 :('/api/owner/lookup?building='+encodeURIComponent(q)+adminKey());
  const d=await api(url);
  const owners=d.owners||[];
  if(!owners.length){$('or').innerHTML='<div class="item">No owner on file for that yet. (DLD area data must be ingested — JVC is loaded.)</div>';return;}
  const note=d.revealed?'':'<div class="warnbox" onclick="setAdminKey()" style="cursor:pointer">Phones masked — tap here to enter your admin key and reveal real numbers.</div>';
  $('or').innerHTML=note+owners.map(r=>`<div class="item"><b>${esc(r.name||'Owner')} · ${esc(r.phone)}</b>
   <span class="dim">${esc([r.building,r.unit&&('unit '+r.unit),r.property_number&&('permit '+r.property_number),r.country].filter(Boolean).join(' · '))}</span></div>`).join('');
 }catch(e){$('or').innerHTML='<div class="item">error: '+esc(e.message)+'</div>';}}
async function loadLeads(){$('lr').innerHTML='<div class="loading">loading…</div>';
 try{const d=await api('/api/leads/recent');
  if(!d.leads||!d.leads.length){$('lr').innerHTML='<div class="item">No group leads captured yet.</div>';return;}
  $('lr').innerHTML=d.leads.map(l=>`<div class="item"><b>${esc(l.contact||l.phone||'lead')}</b><span class="dim">${esc(l.text||l.request||'')}</span></div>`).join('');
 }catch(e){$('lr').innerHTML='<div class="item">error: '+esc(e.message)+'</div>';}}
async function checkDesign(){const p=$('eplot').value,g=$('egfa').value,f=$('efloors').value;
 $('er').innerHTML='<div class="loading">auditing…</div>';
 try{const d=await api('/api/engineering/evaluate?community=palm+jumeirah&plot_area='+encodeURIComponent(p)+'&gfa='+encodeURIComponent(g)+'&floors='+encodeURIComponent(f));
  if(!d.ok){$('er').innerHTML='<div class="item">'+esc(d.verdict||d.error)+'</div>';return;}
  $('er').innerHTML='<div class="item"><b>'+(d.verdict==='breach'?'❌ BREACH':'✅ '+esc(d.verdict))+'</b></div>'+
   d.checks.map(c=>`<div class="item"><span class="pill ${c.status==='complies'?'ok':(c.status==='breach'?'bad':'na')}">${esc(c.status)}</span>
   ${esc(c.rule)} <span class="dim">(limit ${esc(c.limit_label||c.limit)}${c.proposed!==undefined?' / yours '+esc(c.proposed_label||c.proposed):''})</span></div>`).join('');
 }catch(e){$('er').innerHTML='<div class="item">error: '+esc(e.message)+'</div>';}}
async function loadHealth(){$('hr').innerHTML='<div class="loading">checking…</div>';
 try{const d=await api('/api/health/deep');
  $('hr').innerHTML='<div class="item"><b>'+(d.status==='healthy'?'✅ all green':'⚠️ '+esc(d.status))+'</b></div>'+
   Object.entries(d.components).map(([k,v])=>`<div class="item"><span class="pill ${v.ok===true?'ok':(v.ok===false?'bad':'na')}">${v.ok===true?'ok':(v.ok===false?'FAIL':'—')}</span>${esc(k)} <span class="dim">${esc(v.detail||v.value||'')}</span></div>`).join('');
 }catch(e){$('hr').innerHTML='<div class="item">error: '+esc(e.message)+'</div>';}}
$('uq').addEventListener('keydown',e=>{if(e.key==='Enter')findUnits()});
$('oq').addEventListener('keydown',e=>{if(e.key==='Enter')findOwners()});
boot();
</script>
</body>
</html>"""
