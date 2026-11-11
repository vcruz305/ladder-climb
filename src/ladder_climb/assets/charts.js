/* Generic SVG trajectories: no track names, units, or directions are hardcoded. */
(() => {
  'use strict';
  const metadata = new Map();
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = value => Number(value).toLocaleString('en-US',{maximumFractionDigits:3});
  const better = (direction,a,b) => direction === 'lower' ? a < b : a > b;

  function render(trackId, track) {
    const wrap = document.getElementById(`chart-${trackId}`);
    const all = track.rungs || [], W = Math.max(340,Math.round((wrap.clientWidth || 600)-18));
    const H=220,left=47,right=17,top=23,bottom=31;
    if (!all.length) {
      metadata.set(trackId,null);
      return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(track.label)}: no rungs"><text class="axis-text" x="25" y="40">No rungs recorded yet</text></svg>`;
    }
    const xStep=(W-left-right)/Math.max(1,all.length-1), x=i=>left+i*xStep;
    const values=all.map(r=>Number(r.value)).filter(Number.isFinite);
    if (track.baseline !== null) values.push(Number(track.baseline));
    if (track.target !== null) values.push(Number(track.target));
    const rawMax=Math.max(...values,1),rawMin=Math.min(...values,0),spread=Math.max(rawMax-rawMin,1);
    const max=rawMax+spread*.12,min=Math.max(0,rawMin-spread*.12),y=v=>top+(H-top-bottom)*(1-(Number(v)-min)/(max-min));
    let frontier=track.baseline,winners=new Set(),steps=[];
    all.forEach(r=>{
      if(r.status==='kept'&&(frontier===null||better(track.direction,Number(r.value),Number(frontier)))){frontier=Number(r.value);winners.add(r.id)}
      steps.push(frontier);
    });
    let d='',area='';
    steps.forEach((value,i)=>{if(value===null)return;const prefix=d?' L':'M';d+=`${prefix}${i?' H'+x(i):x(i)} V${y(value)}`;area+=`${i?' H'+x(i):'M '+x(i)} V${y(value)}`});
    if(d)area+=` L${x(all.length-1)} ${H-bottom} L${left} ${H-bottom} Z`;
    let grid='';
    [0,.5,1].forEach(f=>{const yy=top+(H-top-bottom)*(1-f),value=min+(max-min)*f;grid+=`<line class="gridline" x1="${left}" x2="${W-right}" y1="${yy}" y2="${yy}"/><text class="axis-text" x="0" y="${yy+3}">${fmt(value)}</text>`});
    let marks='',labels='',lastLabel={x:-999,y:-999};
    all.forEach((r,i)=>{
      const xx=x(i),yy=y(r.value),fy=steps[i]===null?yy:y(steps[i]);
      if(r.status==='kept'){
        const champion=winners.has(r.id),ly=Math.abs(xx-lastLabel.x)<60&&Math.abs(fy-lastLabel.y)<18?fy+18:fy-9;
        marks+=`<circle class="${champion?'winner':'anchor'}" cx="${xx}" cy="${yy}" r="${champion?4:3}"/>`;
        if(champion){labels+=`<text class="value-label" x="${xx}" y="${Math.max(11,ly)}" text-anchor="middle">${fmt(r.value)}</text>`;lastLabel={x:xx,y:ly}}
      }else if(r.status==='testing'){
        marks+=`<g><circle class="testing-ring" cx="${xx}" cy="${yy}" r="5"/><circle class="testing-mark" cx="${xx}" cy="${yy}" r="3.6"/></g>`;
      }else if(r.status==='rejected'){
        marks+=`<path class="rejected-mark" d="M${xx-3} ${yy-3}L${xx+3} ${yy+3}M${xx+3} ${yy-3}L${xx-3} ${yy+3}"/>`;
      }
    });
    const maxTicks=Math.max(2,Math.floor(W/78)),stride=Math.max(1,Math.ceil(all.length/maxTicks));
    const ticks=all.map((r,i)=>(i%stride===0||i===all.length-1||r.status==='testing')?`<text class="axis-text" x="${x(i)}" y="${H-8}" text-anchor="middle">${esc(r.id)}</text>`:'').join('');
    metadata.set(trackId,{all,W,left,right,x,track});
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(track.label)} trajectory in ${esc(track.unit)}">${grid}<path class="frontier-area" d="${area}"/><path class="frontier" d="${d}"/>${marks}${labels}${ticks}<line class="cursor" x1="0" x2="0" y1="${top}" y2="${H-bottom}"/><rect class="chart-hit" x="${left}" y="${top}" width="${W-left-right}" height="${H-top-bottom}"/></svg><div class="tooltip"></div>`;
  }

  function showTip(event) {
    const wrap=event.target.closest('.chart-wrap');if(!wrap)return;
    const id=wrap.id.replace('chart-',''),meta=metadata.get(id);if(!meta)return;
    const rect=wrap.querySelector('svg').getBoundingClientRect(),localX=(event.clientX-rect.left)*meta.W/rect.width;
    let nearest=0,distance=Infinity;meta.all.forEach((r,i)=>{const d=Math.abs(meta.x(i)-localX);if(d<distance){distance=d;nearest=i}});
    const rung=meta.all[nearest],cursor=wrap.querySelector('.cursor');cursor.setAttribute('x1',meta.x(nearest));cursor.setAttribute('x2',meta.x(nearest));cursor.classList.add('active');
    const tip=wrap.querySelector('.tooltip');tip.innerHTML=`<div class="tip-head"><span>${esc(rung.id)} · ${esc(rung.status.toUpperCase())}</span><span>${esc(rung.commit||'working')}</span></div><p class="tip-title">${esc(rung.summary)}</p><span class="tip-value">${fmt(rung.value)} ${esc(meta.track.unit)}</span><p class="tip-meta">${new Date(rung.updated_at).toLocaleString()} · ${esc(rung.gate||'gate not set')}</p>`;
    tip.classList.add('visible');const px=meta.x(nearest)/(meta.W/rect.width)+8;tip.style.left=`${Math.max(8,Math.min(px,wrap.clientWidth-tip.offsetWidth-8))}px`;
  }
  function hideTips(){document.querySelectorAll('.tooltip').forEach(t=>t.classList.remove('visible'));document.querySelectorAll('.cursor').forEach(c=>c.classList.remove('active'))}
  window.LadderCharts={render,showTip,hideTips,esc,fmt,better};
})();
