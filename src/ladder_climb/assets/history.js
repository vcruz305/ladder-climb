/* Cross-model history, campaign navigation, milestones, and archive overlays. */
(() => {
'use strict';
const $=id=>document.getElementById(id),C=window.LadderCharts,fmt=C.fmt;
let workspace=null,offset=0,total=0,filters={},loading=false,requestGeneration=0,controller=null,searchTimer=null;
const model={id:null,board:null,campaign:'active',campaigns:[],review:'all',status:'all',track:'all',order:'newest',search:'',overlay:false,archiveLoading:false};
const archiveCache=new Map(),UI=()=>window.LadderUI;
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
function badge(value){return el('span',value||'pending','badge '+(value||'pending'))}
function deltaNode(abs,pct){if(abs===null||abs===undefined)return el('span','—','delta-badge');const sign=abs>0?'+':'',label=sign+fmt(abs)+(pct===null||pct===undefined?'':' / '+sign+fmt(pct)+'%');return el('span',label,'delta-badge '+(abs>=0?'positive':'negative'))}
function cell(cls,label,value){const td=el('td',undefined,cls);if(label)td.append(el('span',label,'mobile-label'));if(value instanceof Node)td.append(value);else td.append(document.createTextNode(value??'—'));return td}
function detailList(row){const dl=el('dl',undefined,'detail-inner'),fields={'Full title':row.summary,'Commit':row.commit||'working tree','Evidence':JSON.stringify(row.metrics||{}),'Wave / session':(row.wave||'—')+' / '+(row.session||'—'),'Agent / reviewer':(row.agent||'—')+' / '+(row.reviewer||'—'),'Gate / review':(row.gate||'pending')+' / '+(row.review||'pending'),'Started':row.started_at||'—','Ended':row.ended_at||'—','Review notes':row.review_notes||'No review notes.'};Object.entries(fields).forEach(([key,value])=>dl.append(el('dt',key),el('dd',String(value))));return dl}
function toggleDetails(tr,row,count){const next=tr.nextElementSibling;if(next&&next.classList.contains('detail-row')){next.remove();tr.classList.remove('open');tr.setAttribute('aria-expanded','false');return}const detail=el('tr',undefined,'detail-row'),td=el('td');td.colSpan=count;td.append(detailList(row));detail.append(td);tr.after(detail);tr.classList.add('open');tr.setAttribute('aria-expanded','true')}
function expandable(tr,row,count){const toggle=()=>toggleDetails(tr,row,count);tr.addEventListener('click',toggle);tr.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggle()}})}
function globalRow(row,index){
 const tr=el('tr',undefined,'data-row');tr.tabIndex=0;tr.setAttribute('aria-expanded','false');tr.style.setProperty('--track',UI().tone(index));
 tr.append(cell('track-cell','Model',row.model+' / '+row.campaign),cell('rung-cell','Rung',row.track+' / '+row.rung));
 const summary=el('div');summary.append(el('span',row.title||row.summary||'','experiment'),el('span',(row.commit||'working')+' · '+(row.wave||'—')+' · '+(row.session||'—'),'secondary'));
 const metric=el('div');metric.append(el('span',fmt(row.value),'metric-value'),el('span',row.unit,'metric-regime'));
 tr.append(cell('experiment-cell','Experiment',summary),cell('metric-cell num','Result',metric),cell('delta-cell num','Δ prior best',deltaNode(row.delta_abs,row.delta_pct)),cell('updated-cell','Updated',UI().pdt(row.updated_at||row.ended_at)),cell('review-cell','Review',badge(row.review)),cell('status-cell','Status',el('span',row.status,'status '+row.status)),cell('open-cell num','',el('span','›','chevron')));
 expandable(tr,row,9);return tr;
}
function query(extra={}){return new URLSearchParams({...filters,...extra}).toString()}
async function load(append=false){
 if(loading)return;loading=true;const generation=++requestGeneration;if(controller)controller.abort();controller=new AbortController();$('history-status').textContent='Loading history…';
 try{const res=await fetch('/api/history?'+query({limit:200,offset:append?offset:0,sort:'newest'}),{cache:'no-store',signal:controller.signal});if(!res.ok)throw new Error('HTTP '+res.status);const data=await res.json();if(generation!==requestGeneration)return;$('updated').textContent=UI().pdt(data.now);total=data.total;offset=data.offset+data.rows.length;if(!append)$('history-rows').replaceChildren();data.rows.forEach((r,i)=>$('history-rows').append(globalRow(r,i)));if(!data.rows.length&&!append){const tr=el('tr'),td=el('td','No history matches these filters.','empty-row');td.colSpan=9;tr.append(td);$('history-rows').append(tr)}$('history-status').textContent=offset+' of '+total+' results · click any row for metadata';$('history-more').hidden=offset>=total}
 catch(e){if(e.name!=='AbortError')$('history-status').textContent=e.message}finally{if(generation===requestGeneration)loading=false}
}
function refresh(){offset=0;load()}
function buildModelFilters(){const wrap=$('history-model-filters');wrap.replaceChildren();const add=(id,label)=>{const b=el('button',label,'pill');b.dataset.historyModel=id;b.setAttribute('aria-pressed',String((filters.model||'')===id));wrap.append(b)};add('','All Models');(workspace?.models||[]).forEach(m=>add(m.id,m.model_name||m.id))}
function bind(ws){
 workspace=ws;buildModelFilters();
 $('history-search').addEventListener('input',e=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{filters.search=e.target.value.trim();if(!filters.search)delete filters.search;refresh()},220)});
 $('history-model-filters').addEventListener('click',e=>{const b=e.target.closest('[data-history-model]');if(!b)return;if(b.dataset.historyModel)filters.model=b.dataset.historyModel;else delete filters.model;buildModelFilters();refresh()});
 for(const [id,key] of [['history-status-filter','status'],['history-review-filter','review']])$(id).addEventListener('change',e=>{if(e.target.value)filters[key]=e.target.value;else delete filters[key];refresh()});
 $('history-more').addEventListener('click',()=>load(true));
 for(const name of ['json','csv'])$('export-'+name).addEventListener('click',()=>{const a=el('a');a.href='/api/export?'+query({format:name});a.download='ladder-history.'+name;a.click()});
 document.querySelectorAll('[data-review-filter]').forEach(b=>b.addEventListener('click',()=>{model.review=b.dataset.reviewFilter;renderModelHistory()}));
 $('model-status-filters').addEventListener('click',e=>{const b=e.target.closest('[data-model-status]');if(b){model.status=b.dataset.modelStatus;renderModelHistory()}});
 $('history-order').addEventListener('click',()=>{model.order=model.order==='newest'?'chronological':'newest';renderModelHistory()});
 $('model-track-filters').addEventListener('click',e=>{const b=e.target.closest('[data-model-track]');if(b){model.track=b.dataset.modelTrack;renderModelHistory()}});
 $('model-history-search').addEventListener('input',e=>{model.search=e.target.value.trim().toLowerCase();renderModelHistory()});
 $('campaign-strip').addEventListener('click',e=>{if(e.target.closest('[data-overlay]')){model.overlay=!model.overlay;renderCampaigns();renderModelHistory()}});
}
function historyRow(row,index){
 const tr=el('tr',undefined,'data-row');tr.tabIndex=0;tr.setAttribute('aria-expanded','false');tr.style.setProperty('--track',UI().tone(index));
 tr.append(cell('campaign-cell','Campaign / wave',(model.campaign==='active'?'Active Climb':model.campaign)+' / '+(row.wave||'—')),cell('track-cell','Track',el('span',UI().trackName(row.track,{label:row.track}).toUpperCase(),'track-badge')));
 const rung=el('div');rung.append(el('span',row.id,'rung-id'),el('span',row.commit||'working','commit'));
 const summary=el('div');summary.append(el('span',row.title||row.summary||'','experiment'),el('span',UI().evidence(row),'secondary'));
 const metric=el('div');metric.append(el('span',fmt(row.value),'metric-value'),el('span',row.unit,'metric-regime'));
 const review=el('div');review.append(badge(row.review),document.createTextNode(' '),badge(row.gate));
 tr.append(cell('rung-cell','Rung / commit',rung),cell('experiment-cell','Experiment / evidence',summary),cell('metric-cell num','Throughput',metric),cell('delta-cell num','Δ prior best',deltaNode(row._delta?.abs,row._delta?.pct)),cell('updated-cell','Updated',UI().pdt(row.updated_at)),cell('duration-cell','Duration',UI().rungDuration(row)),cell('review-cell','Review / gate',review),cell('status-cell','Status',el('span',row.status,'status '+row.status)),cell('open-cell num','',el('span','›','chevron')));
 expandable(tr,row,11);return tr;
}
function renderModelFilters(entries){
 const wrap=$('model-track-filters');wrap.replaceChildren();const add=(id,label)=>{const b=el('button',label,'pill');b.dataset.modelTrack=id;b.setAttribute('aria-pressed',String(model.track===id));wrap.append(b)};add('all','All Tracks');entries.forEach(([id,t])=>add(id,UI().trackName(id,t)));
 document.querySelectorAll('[data-model-status]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.modelStatus===model.status)));
 document.querySelectorAll('[data-review-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.reviewFilter===model.review)));
 $('history-order').textContent=model.order==='newest'?'Newest First':'Chronological';$('history-order').dataset.order=model.order;
}
function campaignCount(c){return Object.values(c.rungs||{}).reduce((n,v)=>n+Number(v||0),0)}
function renderCampaigns(){
 const strip=$('campaign-strip');strip.replaceChildren();
 model.campaigns.forEach(c=>{const id=c.active?'active':c.campaign_id,b=el('button',undefined,'campaign-card');b.dataset.campaign=id;b.setAttribute('aria-pressed',String(id===model.campaign));const champions=Object.values(c.champions||{}).map(v=>fmt(v.value)+' '+(v.unit||'')).join(' · ');b.append(el('strong',c.active?'Active Climb':c.campaign_id),el('span',c.active?'LIVE · REVISION '+(model.board?.revision||0):(campaignCount(c)+' RUNGS · '+(champions||'IMMUTABLE ARCHIVE'))));strip.append(b)});
 const archives=model.campaigns.filter(c=>!c.active),toggle=el('button',model.overlay?'Overlay Archives · ON':'Overlay Archives','pill overlay-toggle');toggle.dataset.overlay='true';toggle.setAttribute('aria-pressed',String(model.overlay));toggle.disabled=!archives.length||model.campaign!=='active';strip.append(toggle);
}
function archiveKey(){return model.id+':'+model.campaigns.filter(c=>!c.active).map(c=>c.campaign_id).join(',')}
async function ensureArchives(){
 if(!model.overlay||model.campaign!=='active'||model.archiveLoading||archiveCache.has(archiveKey()))return;
 const key=archiveKey(),id=model.id;model.archiveLoading=true;
 try{const boards=await Promise.all(model.campaigns.filter(c=>!c.active).map(async c=>{const res=await fetch('/api/models/'+encodeURIComponent(id)+'/ladder.json?campaign='+encodeURIComponent(c.campaign_id),{cache:'no-store'});if(!res.ok)throw new Error('Archive HTTP '+res.status);return res.json()}));archiveCache.set(key,boards);if(model.id===id&&archiveKey()===key)renderModelHistory()}
 catch(e){console.warn('Archive overlays unavailable',e)}finally{model.archiveLoading=false}
}
function milestone(label,value){const cell=el('div',undefined,'milestone');cell.append(el('span',label,'milestone-label'),el('strong',value,'milestone-value'));return cell}
function renderMilestones(entries){
 const rows=entries.flatMap(([,t])=>t.rungs),kept=rows.filter(r=>r.status==='kept').length,verified=rows.filter(r=>r.review==='verified').length,gates=rows.filter(r=>['pass','passed'].includes(String(r.gate||'').toLowerCase())).length,seconds=rows.reduce((n,r)=>n+Number(r.duration_s||0),0);
 const archives=model.campaigns.filter(c=>!c.active).length,legacy=!verified&&!gates;
 const champions=entries.map(([id,t])=>{const best=C.champion(t).best;return UI().trackName(id,t)+' '+fmt(t.baseline)+' → '+fmt(best)}).join(' · ');
 const summary=$('model-history-summary');summary.replaceChildren(milestone('Baseline → best',champions),milestone('Kept / explored (hit %)',kept+' / '+rows.length+' ('+(rows.length?fmt(kept/rows.length*100):'0')+'%)'),milestone('Total climb time',UI().duration(seconds)),milestone(legacy?'Archives & waves':'Verified / gate pass',legacy?'GATE PASS / KEPT: '+(gates||kept)+' / '+rows.length+' · '+archives+' ARCHIVES':verified+' / '+gates));
}
function championHeader(track,index){const c=C.champion(track),champ=el('div',undefined,'champion'),best=el('strong');best.append(document.createTextNode(fmt(c.best)),el('small',String(track.unit||'value').toUpperCase()));const gain=C.improvement(track,c.best),label=el('span',(gain===null?'—':(gain>=0?'+':'')+fmt(gain)+'%')+' VS '+fmt(track.baseline)+' '+String(track.unit||'').toUpperCase()+' BASE');champ.append(best,label);return champ}
function renderCharts(entries){
 const charts=$('frontier-chart');charts.replaceChildren();const overlays=model.overlay&&model.campaign==='active'?(archiveCache.get(archiveKey())||[]):[];
 entries.forEach(([trackId,track],index)=>{const card=el('article',undefined,'panel track-panel '+(index===0?'prefill':index===1?'decode':index===2?'track-3':'track-'+(index+1)));card.style.setProperty('--track',UI().tone(index));const head=el('div',undefined,'panel-head'),title=el('div');title.append(el('span','TRACK '+String(index+1).padStart(2,'0')+' / CAMPAIGN HISTORY','panel-kicker'),el('h3',UI().trackName(trackId,track).toUpperCase()+' RISING LADDER','track-title'));head.append(title,championHeader(track,index));const wrap=el('div',undefined,'chart-wrap track-panel');wrap.id='frontier-'+trackId;wrap.style.setProperty('--track',UI().tone(index));card.append(head,wrap);charts.append(card);C.renderInto(wrap,wrap.id,track,true,overlays.map(b=>b.tracks?.[trackId]).filter(Boolean))});
}
function renderModelHistory(){
 if(!model.board)return;const entries=Object.entries(model.board.tracks||{});renderModelFilters(entries);renderCampaigns();renderMilestones(entries);renderCharts(entries);ensureArchives();
 const allRows=[];entries.forEach(([trackId,track],index)=>{const ds=C.deltas(track);[...track.rungs].sort((a,b)=>Date.parse(a.updated_at||0)-Date.parse(b.updated_at||0)).forEach(r=>allRows.push({...r,track:trackId,unit:track.unit,_index:index,_delta:ds[r.id]}))});
 const filtered=allRows.filter(r=>{const haystack=[r.id,r.summary,r.commit,r.wave,r.session,UI().evidence(r)].join(' ').toLowerCase();return(model.track==='all'||r.track===model.track)&&(model.status==='all'||r.status===model.status)&&(model.review==='all'||(r.review||'pending')===model.review)&&(!model.search||haystack.includes(model.search))});
 filtered.sort((a,b)=>{const delta=Date.parse(a.updated_at||0)-Date.parse(b.updated_at||0);return model.order==='newest'?-delta:delta});const body=$('model-history-rows');body.replaceChildren();filtered.forEach(r=>body.append(historyRow(r,r._index)));if(!filtered.length){const tr=el('tr'),td=el('td','No history matches these filters.','empty-row');td.colSpan=11;tr.append(td);body.append(tr)}$('model-history-count').textContent=filtered.length+' / '+allRows.length+' RUNGS';
}
function campaigns(list,selected){model.campaigns=list;model.campaign=selected;renderCampaigns()}
function modelHistory(board,campaign,id){model.board=board;model.campaign=campaign;model.id=id||board.model;if(![...Object.keys(board.tracks||{}),'all'].includes(model.track))model.track='all';renderModelHistory()}
window.LadderHistory={bind,load,campaigns,modelHistory};
})();
