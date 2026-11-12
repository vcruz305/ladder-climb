/* Stepped frontiers, archive overlays, compact sparklines, and chart probes. */
(() => {
'use strict';
const metadata=new Map();
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>v===null||v===undefined||!Number.isFinite(Number(v))?'—':Number(v).toLocaleString('en-US',{maximumFractionDigits:2});
const better=(direction,a,b)=>direction==='lower'?a<b:a>b;
function champion(track){let best=null,winner=null;(track.rungs||[]).forEach(r=>{const value=Number(r.value);if(r.status==='kept'&&Number.isFinite(value)&&(best===null||better(track.direction,value,best))){best=value;winner=r}});return{best,winner}}
function improvement(track,best){const base=Number(track.baseline);if(best===null||!Number.isFinite(base)||base===0)return null;return(track.direction==='lower'?base-best:best-base)/Math.abs(base)*100}
function deltas(track){
 const ordered=[...(track.rungs||[])].sort((a,b)=>Date.parse(a.started_at||a.updated_at||0)-Date.parse(b.started_at||b.updated_at||0));
 let best=track.baseline===null||track.baseline===undefined?null:Number(track.baseline),prior=null;const out={};
 ordered.forEach(r=>{const value=Number(r.value),old=best,oldId=prior;let abs=null,pct=null;if(Number.isFinite(value)&&best!==null&&Number.isFinite(best)){abs=value-best;if(best!==0)pct=abs/Math.abs(best)*100}if(r.status==='kept'&&Number.isFinite(value)&&(best===null||better(track.direction,value,best))){best=value;prior=r.id}out[r.id]={abs,pct,prior_id:oldId,prior_value:old}});
 return out;
}
function deltaText(d){if(!d||d.abs===null||d.abs===undefined||!Number.isFinite(Number(d.abs)))return'—';const sign=d.abs>0?'+':'',pct=d.pct===null||d.pct===undefined?'':sign+fmt(d.pct)+'%';return sign+fmt(d.abs)+(pct?' / '+pct:'')}
function highWater(track,all){let best=null;return all.map(r=>{const value=Number(r.value);if(r.status==='kept'&&Number.isFinite(value)&&(best===null||better(track.direction,value,best)))best=value;return best===null?Number(track.baseline)||0:best})}
function stepped(values,count,left,right,top,bottom,W,H,y){if(!values.length)return'';const step=(W-left-right)/Math.max(count-1,1),x=i=>left+i*step;let d='M '+x(0)+' '+y(values[0]);for(let i=1;i<values.length;i++)d+=' H '+x(i)+' V '+y(values[i]);return d}
function renderInto(wrap,id,track,frontierOnly=false,archives=[]){
 const all=(track.rungs||[]).filter(r=>Number.isFinite(Number(r.value))),W=Math.max(340,Math.round((wrap.clientWidth||656)-16)),H=216,left=43,right=17,top=24,bottom=30;
 metadata.delete(id);wrap.dataset.generation=String(Date.now()+Math.random());
 if(!all.length){wrap.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc(track.label)+': no rungs"><text class="axis-text" x="20" y="30">No rungs recorded</text></svg>';return}
 const archiveValues=archives.flatMap(t=>(t.rungs||[]).map(r=>Number(r.value)).filter(Number.isFinite));
 const rawMax=Math.max(Number(track.baseline)||0,...all.map(r=>Number(r.value)||0),...archiveValues,1),max=rawMax*1.13,y=v=>top+(H-top-bottom)*(1-(Number(v)||0)/max);
 const frontier=highWater(track,all),xStep=(W-left-right)/Math.max(all.length-1,1),x=i=>left+i*xStep;
 let d=stepped(frontier,all.length,left,right,top,bottom,W,H,y),area=d+' L '+x(all.length-1)+' '+(H-bottom)+' L '+x(0)+' '+(H-bottom)+' Z';
 const overlay=archives.map(t=>{const rows=(t.rungs||[]).filter(r=>Number.isFinite(Number(r.value)));return'<path class="archive-frontier" d="'+stepped(highWater(t,rows),rows.length,left,right,top,bottom,W,H,y)+'"/>'}).join('');
 let grid='';[0,.5,1].forEach(f=>{const yy=top+(H-top-bottom)*(1-f);grid+='<line class="gridline" x1="'+left+'" x2="'+(W-right)+'" y1="'+yy+'" y2="'+yy+'"/><text class="axis-text" x="0" y="'+(yy+3)+'">'+fmt(max*f)+'</text>'});
 let best=null,winners=new Set();all.forEach(r=>{const value=Number(r.value);if(r.status==='kept'&&Number.isFinite(value)&&(best===null||better(track.direction,value,best))){best=value;winners.add(r.id)}});
 let marks='',labels='',lastLabel={x:-999,y:-999,level:0};
 all.forEach((r,i)=>{const xx=x(i),yy=y(r.value),yyFrontier=y(frontier[i]);if(winners.has(r.id)){let ly=Math.max(11,yyFrontier-9),anchor='middle',tx=xx,level=0;if(xx<left+20){anchor='start';tx=xx-2}else if(xx>W-right-20){anchor='end';tx=xx+2}if(Math.abs(xx-lastLabel.x)<63&&Math.abs(ly-lastLabel.y)<17){level=lastLabel.level?0:1;ly=level?Math.min(H-bottom-13,yyFrontier+18):Math.max(11,yyFrontier-22)}if(ly>yyFrontier+3)labels+='<line class="leader" x1="'+xx+'" y1="'+(yyFrontier+4)+'" x2="'+tx+'" y2="'+(ly-3)+'"/>';labels+='<text class="value-label" x="'+tx+'" y="'+ly+'" text-anchor="'+anchor+'">'+fmt(r.value)+'</text>';lastLabel={x:tx,y:ly,level};marks+='<circle class="winner" cx="'+xx+'" cy="'+yy+'" r="3.8"/>'}else if(r.status==='kept')marks+='<circle class="anchor" cx="'+xx+'" cy="'+yy+'" r="3"/>';else if(r.status==='testing'&&!frontierOnly)marks+='<circle class="testing-ring" cx="'+xx+'" cy="'+yy+'" r="5"/><circle class="testing-mark" cx="'+xx+'" cy="'+yy+'" r="3.6"/>';else if(!frontierOnly)marks+='<path class="rejected-mark" d="M '+(xx-2.7)+' '+(yy-2.7)+' L '+(xx+2.7)+' '+(yy+2.7)+' M '+(xx+2.7)+' '+(yy-2.7)+' L '+(xx-2.7)+' '+(yy+2.7)+'"/>'});
 const maxTicks=Math.max(3,Math.floor((wrap.clientWidth||600)/82)),stride=Math.max(1,Math.ceil(all.length/maxTicks));let ticks=[];all.forEach((r,i)=>{if(i%stride===0||i===all.length-1||r.status==='testing')ticks.push(i)});ticks=[...new Set(ticks)].sort((a,b)=>a-b);for(let i=ticks.length-2;i>=0;i--)if(x(ticks[i+1])-x(ticks[i])<43)ticks.splice(i,1);
 const tickLabels=ticks.map(i=>'<text class="axis-text" x="'+x(i)+'" y="'+(H-8)+'" text-anchor="middle">'+esc(all[i].id)+'</text>').join(''),ds=deltas(track);
 wrap.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc(track.label)+' rising ladder in '+esc(track.unit)+'" data-chart="'+esc(id)+'">'+grid+overlay+'<path class="frontier-area" d="'+area+'"/><path class="frontier" d="'+d+'"/>'+marks+labels+tickLabels+'<line class="cursor" x1="0" x2="0" y1="'+top+'" y2="'+(H-bottom)+'"/><rect class="chart-hit" x="'+left+'" y="'+top+'" width="'+(W-left-right)+'" height="'+(H-top-bottom)+'"/></svg><div class="chart-tooltip"></div>';
 metadata.set(id,{all,W,H,left,right,top,bottom,x,y,track,ds,generation:wrap.dataset.generation});
}
function miniSparkline(track){
 const rows=(track.rungs||[]).filter(r=>Number.isFinite(Number(r.value))),values=highWater(track,rows),all=[Number(track.baseline)||0,...values],W=280,H=68,left=2,right=2,top=5,bottom=5,max=Math.max(...all,1)*1.06,y=v=>top+(H-top-bottom)*(1-v/max),x=i=>left+i*(W-left-right)/Math.max(all.length-1,1);
 let d='M '+x(0)+' '+y(all[0]);for(let i=1;i<all.length;i++)d+=' H '+x(i)+' V '+y(all[i]);const area=d+' L '+x(all.length-1)+' '+(H-bottom)+' L '+x(0)+' '+(H-bottom)+' Z',best=champion(track).best,gain=improvement(track,best);
 return{svg:'<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+esc(track.label)+' champion frontier"><path class="mini-area" d="'+area+'"/><path class="mini-line" d="'+d+'"/></svg>',best,gain};
}
function showTip(event){const wrap=event.target.closest('.chart-wrap');if(!wrap)return;const meta=metadata.get(wrap.id);if(!meta||wrap.dataset.generation!==meta.generation)return;const rect=wrap.querySelector('svg').getBoundingClientRect();if(!rect.width)return;const sx=meta.W/rect.width,localX=(event.clientX-rect.left)*sx;let nearest=0,dist=Infinity;meta.all.forEach((r,i)=>{const d=Math.abs(meta.x(i)-localX);if(d<dist){dist=d;nearest=i}});const r=meta.all[nearest],xx=meta.x(nearest),cursor=wrap.querySelector('.cursor');cursor.setAttribute('x1',xx);cursor.setAttribute('x2',xx);cursor.classList.add('active');const tip=wrap.querySelector('.chart-tooltip');tip.innerHTML='<div class="tip-head"><span>'+esc(r.id)+' · '+esc(String(r.status).toUpperCase())+'</span><span>'+esc(r.commit||'working')+'</span></div><p class="tip-title">'+esc(r.summary||'')+'</p><span class="tip-metric">'+fmt(r.value)+' <small>'+esc(r.unit||meta.track.unit)+'</small></span><span class="tip-delta">'+esc(deltaText(meta.ds[r.id]))+'</span><p class="tip-time">'+esc(r.updated_at||'—')+' · '+esc(r.duration_s??'running')+'</p>'+(r.wave?'<p class="tip-secondary">'+esc(r.wave)+' · '+esc(r.session||'—')+' · '+esc(r.review||'pending')+'</p>':'');tip.classList.add('visible');const px=xx/sx+8,left=Math.max(8,Math.min(px,wrap.clientWidth-tip.offsetWidth-8));tip.style.left=left+'px'}
function hideTips(){document.querySelectorAll('.chart-tooltip').forEach(t=>t.classList.remove('visible'));document.querySelectorAll('.cursor').forEach(c=>c.classList.remove('active'))}
window.LadderCharts={renderInto,showTip,hideTips,fmt,better,champion,improvement,deltas,deltaText,miniSparkline,esc};
})();
