/* Live board rendering, filters, timestamps, KPIs, and activity. */
(() => {
  'use strict';
  const {render:renderChart,showTip,hideTips,esc,fmt,better}=window.LadderCharts;
  const FEED_URL=/^https?:$/.test(location.protocol)?'/ladder.json':'http://127.0.0.1:18999/ladder.json';
  const PALETTE=['#7dd3fc','#7ee787','#c4b5fd','#f9a8d4','#fbbf24','#5eead4','#fca5a5','#93c5fd'];
  const defaults={track:'all',status:'all',timezone:'America/Los_Angeles'};
  let prefs={...defaults},state=null,lastPayload='';
  try{prefs={...prefs,...JSON.parse(localStorage.getItem('ladder-climb-v1')||'{}')}}catch(_){}
  if(!['all','kept','rejected','testing'].includes(prefs.status))prefs.status='all';
  if(!['America/Los_Angeles','local','UTC'].includes(prefs.timezone))prefs.timezone=defaults.timezone;
  const $=id=>document.getElementById(id);
  const save=()=>{try{localStorage.setItem('ladder-climb-v1',JSON.stringify(prefs))}catch(_){}};
  const color=index=>PALETTE[index%PALETTE.length];
  const duration=seconds=>{seconds=Math.max(0,Number(seconds)||0);if(seconds<60)return `${seconds<10&&seconds%1?seconds.toFixed(1):Math.floor(seconds)}s`;const m=Math.floor(seconds/60),s=Math.floor(seconds%60);return m<60?`${m}m ${s}s`:`${Math.floor(m/60)}h ${m%60}m ${s}s`};
  const elapsed=r=>{const start=Date.parse(r.started_at);return Number.isFinite(start)?Math.max(0,(Date.now()-start)/1000):0};
  const durationText=r=>r.status==='testing'?`${duration(elapsed(r))} ↻`:(r.duration_s===null||r.duration_s===undefined?'—':duration(r.duration_s));
  const zone=()=>prefs.timezone==='local'?undefined:prefs.timezone;
  const zoneName=()=>prefs.timezone==='local'?'Local':prefs.timezone==='UTC'?'UTC':'PT';
  const formatDate=iso=>{const ms=Date.parse(iso);if(!Number.isFinite(ms))return '—';return new Intl.DateTimeFormat('en-US',{timeZone:zone(),year:'numeric',month:'short',day:'2-digit',hour:'numeric',minute:'2-digit',second:'2-digit',timeZoneName:'short'}).format(ms)};
  const metrics=r=>Object.entries(r.metrics||{}).map(([k,v])=>`${k}: ${typeof v==='object'?JSON.stringify(v):v}`).join(' · ');
  function champion(track){let best=track.baseline,winner=null;(track.rungs||[]).forEach(r=>{if(r.status==='kept'&&(best===null||better(track.direction,Number(r.value),Number(best)))){best=Number(r.value);winner=r}});return {best,winner}}
  function gain(track,best){const base=track.baseline;if(best===null||base===null||!Number(base))return '—';const factor=track.direction==='lower'?base/best:best/base;const pct=track.direction==='lower'?(base-best)/base*100:(best-base)/base*100;return `${factor.toFixed(2)}× · ${pct>=0?'+':''}${pct.toFixed(1)}%`}
  function targetProgress(track,best){const base=track.baseline,target=track.target;if(best===null||target===null||base===null||target===base)return null;const raw=(best-base)/(target-base);return Math.max(0,Math.min(100,raw*100))}
  function deltaMap(track){let best=track.baseline;const result={};(track.rungs||[]).forEach(r=>{const value=Number(r.value);let text='—',kind='';if(best!==null&&Number(best)!==0){const pct=track.direction==='lower'?(best-value)/Math.abs(best)*100:(value-best)/Math.abs(best)*100;text=`${pct>=0?'+':''}${pct.toFixed(1)}%`;kind=pct>0?'good':pct<0?'bad':''}result[r.id]={text,kind};if(r.status==='kept'&&(best===null||better(track.direction,value,Number(best))))best=value});return result}
  function card(id,track,index){
    const {best,winner}=champion(track),progress=targetProgress(track,best),counts={kept:0,rejected:0,testing:0};
    track.rungs.forEach(r=>counts[r.status]=(counts[r.status]||0)+1);
    return `<article class="panel track-card" data-track-card="${esc(id)}" style="--accent:${color(index)}" ${prefs.track!=='all'&&prefs.track!==id?'hidden':''}>
      <div class="panel-head"><div><p class="eyebrow">Track ${String(index+1).padStart(2,'0')} · ${esc(track.direction)} is better</p><h2 class="track-title">${esc(track.label)}</h2></div><div class="champion"><strong>${best===null?'—':fmt(best)}</strong><small>${esc(track.unit)} · CURRENT CHAMPION</small></div></div>
      <div class="kpis"><div class="kpi"><span class="kpi-label">Baseline</span><span class="kpi-value">${track.baseline===null?'—':fmt(track.baseline)+' '+esc(track.unit)}</span></div><div class="kpi"><span class="kpi-label">Gain</span><span class="kpi-value">${gain(track,best)}</span></div><div class="kpi"><span class="kpi-label">Kept / explored</span><span class="kpi-value">${counts.kept} / ${track.rungs.length}</span></div></div>
      <div class="progress" title="Target progress"><div class="progress-bar" style="width:${progress===null?0:progress}%"></div></div>
      <div class="legend"><span>${track.target===null?'No target':`Target ${fmt(track.target)} ${esc(track.unit)}`}${progress===null?'':` · ${progress.toFixed(0)}%`}</span><span>${counts.testing} testing · ${counts.rejected} rejected</span></div>
      <div class="chart-wrap" id="chart-${esc(id)}"></div>
      <div class="legend"><span><i></i>kept champion</span><span><i class="live-dot"></i>testing</span><span>× rejected</span></div>
      <div class="legend"><span>${winner?`Champion ${esc(winner.id)} · ${esc(winner.summary)}`:'No measured champion yet'}</span></div>
      ${winner&&metrics(winner)?`<div class="legend"><span>${esc(metrics(winner))}</span></div>`:''}
    </article>`;
  }
  function worker(id,track,index){const active=track.rungs.filter(r=>r.status==='testing').sort((a,b)=>Date.parse(b.started_at)-Date.parse(a.started_at))[0],best=champion(track);return `<div class="worker ${active?'testing':''}" style="--accent:${color(index)}"><span class="beacon"></span><div><span class="worker-label">${esc(track.label)} climber</span><span class="worker-copy">${active?`<strong>${esc(active.id)}</strong>${esc(active.summary)}`:best.winner?`<strong>${esc(best.winner.id)}</strong>Champion · ${esc(best.winner.summary)}`:'Waiting for first rung'}</span></div><span class="worker-state" ${active?`data-started="${esc(active.started_at)}"`:''}>${active?durationText(active):best.winner?'CHAMPION':'IDLE'}</span></div>`}
  function row(r,id,track,index,deltas){
    const delta=deltas[r.id]||{text:'—',kind:''};return `<tr class="data-row" style="--accent:${color(index)}"><td><span class="track-badge">${esc(id)}</span></td><td><span class="rung-id">${esc(r.id)}</span>${r.commit?`<span class="commit">${esc(r.commit)}</span>`:''}</td><td><span class="experiment">${esc(r.summary)}</span><span class="secondary">${esc(metrics(r)||'No secondary metrics')}</span></td><td class="num"><span class="metric-value">${fmt(r.value)}</span><span class="metric-unit">${esc(r.unit)}</span></td><td class="num"><span class="mobile-label">Δ prior champion</span><span class="delta ${delta.kind}">${delta.text}</span></td><td class="updated"><span class="mobile-label">Updated · ${zoneName()}</span><time datetime="${esc(r.updated_at)}">${esc(formatDate(r.updated_at))}</time></td><td class="duration"><span class="mobile-label">Duration</span><span class="${r.status==='testing'?'live-time':''}" ${r.status==='testing'?`data-started="${esc(r.started_at)}"`:''}>${durationText(r)}</span></td><td><span class="gate ${esc(r.gate||'pending')}">${esc(r.gate||'pending')}</span></td><td><span class="status ${esc(r.status)}">${esc(r.status)}</span></td></tr>`;
  }
  function render(data){
    state=data;$('title').textContent=data.title;$('subtitle').textContent=data.subtitle;document.title=`${data.title} · Ladder Climb`;
    const entries=Object.entries(data.tracks);if(prefs.track!=='all'&&!data.tracks[prefs.track])prefs.track='all';
    $('workers').innerHTML=entries.map(([id,t],i)=>worker(id,t,i)).join('');
    $('track-filters').innerHTML=`<span class="control-label">Track</span><button class="track-filter" data-track="all" aria-pressed="${prefs.track==='all'}">ALL (${entries.reduce((n,[,t])=>n+t.rungs.length,0)})</button>`+entries.map(([id,t],i)=>`<button class="track-filter" style="--accent:${color(i)}" data-track="${esc(id)}" aria-pressed="${prefs.track===id}">${esc(t.label)} (${t.rungs.length})</button>`).join('');
    document.querySelectorAll('[data-status]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.status===prefs.status)));$('timezone').value=prefs.timezone;
    $('tracks').innerHTML=entries.map(([id,t],i)=>card(id,t,i)).join('');entries.forEach(([id,t])=>{const wrap=$(`chart-${id}`);wrap.innerHTML=renderChart(id,t)});
    let rows=[];entries.forEach(([id,t],i)=>{if(prefs.track==='all'||prefs.track===id){const deltas=deltaMap(t);t.rungs.forEach(r=>{if(prefs.status==='all'||prefs.status===r.status)rows.push({r,id,t,i,deltas})})}});
    rows.sort((a,b)=>Date.parse(b.r.updated_at)-Date.parse(a.r.updated_at));
    $('activity-rows').innerHTML=rows.length?rows.map(x=>row(x.r,x.id,x.t,x.i,x.deltas)).join(''):'<tr><td colspan="9" class="empty">No rungs match this filter.</td></tr>';
    $('activity-count').textContent=`${rows.length} visible · ${zoneName()}`;
    const all=entries.flatMap(([,t])=>t.rungs),counts={kept:0,rejected:0,testing:0};all.forEach(r=>counts[r.status]=(counts[r.status]||0)+1);
    $('totals').textContent=`${counts.kept} KEPT · ${counts.testing} TESTING · ${counts.rejected} REJECTED · ${all.length} TOTAL`;$('updated').textContent=formatDate(data.updated_at);$('updated').dateTime=data.updated_at;
  }
  function tick(){document.querySelectorAll('[data-started]').forEach(el=>{const ms=Date.parse(el.dataset.started);el.textContent=`${duration(Number.isFinite(ms)?Math.max(0,(Date.now()-ms)/1000):0)} ↻`})}
  async function poll(){try{const response=await fetch(FEED_URL,{cache:'no-store'});if(!response.ok)throw new Error(response.status);const data=await response.json(),payload=JSON.stringify(data);if(payload!==lastPayload){lastPayload=payload;render(data)}$('heartbeat').classList.remove('stale');$('live-label').textContent='LIVE · 2S POLL'}catch(_){$('heartbeat').classList.add('stale');$('live-label').textContent='FEED STALE · RETRYING'}}
  document.addEventListener('click',event=>{const track=event.target.closest('[data-track]'),status=event.target.closest('[data-status]');if(track){prefs.track=track.dataset.track;save();render(state)}if(status){prefs.status=status.dataset.status;save();render(state)}});
  $('timezone').addEventListener('change',event=>{prefs.timezone=event.target.value;save();render(state)});
  $('tracks').addEventListener('pointermove',event=>{if(event.pointerType==='mouse')showTip(event)});$('tracks').addEventListener('pointerdown',showTip);$('tracks').addEventListener('pointerleave',event=>{if(event.pointerType==='mouse')hideTips()},true);
  let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>state&&render(state),120)});
  poll();setInterval(poll,2000);setInterval(tick,1000);
})();
