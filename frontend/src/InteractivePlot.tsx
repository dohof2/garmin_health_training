import { memo, useEffect, useId, useMemo, useRef, useState } from 'react';
import type { ChartResult } from './GraphCanvas';

const label = (id: string) => id.replace('activity_', 'Activity ').replace('vo2_', 'VO₂ max · ').replaceAll('_', ' ');
const seriesColours = ['#356799', '#d16b22', '#27836b', '#8258b6', '#ba4768', '#767221', '#397f97', '#6c5060'];
const elapsedLabel = (seconds: number) => { const total = Math.max(0, Math.round(seconds)); const minutes = Math.floor(total / 60), remainder = String(total % 60).padStart(2, '0'); return minutes >= 60 ? `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}:${remainder}` : `${minutes}:${remainder}`; };
type View = { minX: number; maxX: number; minY: number; maxY: number };
type Pixel = { x: number; y: number };

function InteractivePlot({ result: originalResult, width, height }: { result: ChartResult; width: number; height: number }) {
  const result = useMemo(() => {
    const styles: Record<string,{label:string;colors:string[]}> = {
      'stream:power': {label:'Power',colors:['#356799','#234b76','#6092bf','#173553']},
      'stream:speed': {label:'Speed',colors:['#27836b','#185c4c','#50a58e','#123e34']},
      'stream:heart_rate': {label:'Heart rate',colors:['#c44550','#94303d','#dc7580','#6c2330']},
      'stream:cadence': {label:'Cadence',colors:['#8258b6','#61418c','#a284cb','#432b66']},
    };
    const style=styles[originalResult.spec.metric];
    if(!style||!originalResult.series)return originalResult;
    const multiple=originalResult.series.length>1;
    return {...originalResult,series:originalResult.series.map((series,index)=>({...series,
      label:multiple?`${style.label} · ${series.label}`:style.label,
      color:style.colors[index%style.colors.length],
    }))};
  }, [originalResult]);
  const [view, setView] = useState<View | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [drag, setDrag] = useState<{ start: Pixel; end: Pixel } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const clipId = 'plot-clip-' + useId().replace(/[^a-zA-Z0-9_-]/g, '');
  useEffect(() => { setView(null); setHoverIndex(null); setDrag(null); }, [result]);
  const scatter = result.spec.kind === 'scatter';
  const timestampAxis=result.spec.x_metric==='recorded_time';
  const elapsedAxis = result.spec.x_metric === 'elapsed_time';
  const timeAxis = !elapsedAxis && (!scatter || result.spec.x_metric === 'date');
  const seriesIndex = (id?: string) => Math.max(0, result.series?.findIndex(s => s.id === id) ?? 0);
  const seriesColour = (id?: string) => result.series?.find(s => s.id === id)?.color ?? seriesColours[seriesIndex(id) % seriesColours.length];
  const points = useMemo(()=>result.points.map(p => ({ ...p, nx: !timeAxis ? Number(p.x) : timestampAxis ? Date.parse(String(p.x)) : Date.parse(p.date + 'T00:00:00Z') })),[result.points,timeAxis,timestampAxis]);
  const analysis = result.analysis;
  const trend = analysis?.trend;
  const multiSeries=Boolean(result.series);
  const xs = points.map(p => p.nx), ys = [...points.map(p => p.y), ...(result.range_band?.points.flatMap(p=>[p.low,p.high]) ?? []), ...(analysis?.reference_lines.map(p => p.value) ?? []), ...(trend ? [trend.y_start, trend.y_end] : [])];
  const rawMinX = result.x_domain ? Date.parse(result.x_domain[0]+'T00:00:00Z') : elapsedAxis ? 0 : Math.min(...xs), rawMaxX = result.x_domain ? Date.parse(result.x_domain[1]+'T00:00:00Z') : Math.max(...xs);
  const rawMinY = result.spec.kind === 'bar' ? Math.min(0,...ys) : Math.min(...ys), rawMaxY = Math.max(...ys);
  const meanY = points.reduce((sum, point) => sum + point.y, 0) / points.length;
  const standardDeviation = Math.sqrt(points.reduce((sum, point) => sum + (point.y - meanY) ** 2, 0) / points.length);
  const padding = standardDeviation > 0 ? standardDeviation * .5 : Math.max(1, Math.abs(rawMaxY) * .05);
  const full: View = { minX: rawMinX === rawMaxX ? rawMinX - (timeAxis ? 43200000 : .5) : rawMinX, maxX: rawMinX === rawMaxX ? rawMaxX + (timeAxis ? 43200000 : .5) : rawMaxX, minY: rawMinY - padding, maxY: rawMaxY + padding };
  const { minX, maxX, minY, maxY } = view ?? full;
  const xSpan = maxX-minX || (!timeAxis ? 1 : 86400000), ySpan = maxY-minY || Math.max(1, Math.abs(maxY)*.1);
  const left=64, right=width-18, top=32, bottom=height-65;
  const x = (v:number) => minX === maxX ? (left+right)/2 : left + 8 + (v-minX)/xSpan*(right-left-16);
  const y = (v:number) => bottom-8-(v-minY+ySpan*.08)/(ySpan*1.16)*(bottom-top-16);
  const number = (n:number) => n.toLocaleString(undefined, {maximumFractionDigits:1});
  const tickX = (n:number) => timestampAxis ? new Date(n).toLocaleTimeString([], {timeZone:result.spec.timezone,hour:'2-digit',minute:'2-digit'}) : elapsedAxis ? elapsedLabel(n) : !timeAxis ? number(n) : new Date(n).toLocaleDateString(undefined,{month:'short',...(xSpan<=93*86400000 ? {day:'numeric' as const} : {year:'2-digit' as const}),timeZone:'UTC'});
  const segments: typeof points[] = [];
  points.forEach((p,i) => { if (!i || (multiSeries || timestampAxis ? p.series_id !== points[i-1].series_id || p.segment !== points[i-1].segment : p.nx-points[i-1].nx > 7*86400000)) segments.push([]); segments[segments.length-1].push(p); });
  const clampRange = (low: number, high: number, fullLow: number, fullHigh: number): [number, number] => {
    const span = Math.min(high - low, fullHigh - fullLow);
    const minimum = Math.max(fullLow, Math.min(low, fullHigh - span));
    return [minimum, minimum + span];
  };
  const zoom = (factor: number) => {
    const centerX = (minX + maxX) / 2, centerY = (minY + maxY) / 2;
    const spanX = Math.max((full.maxX - full.minX) / 10000, xSpan * factor), spanY = Math.max((full.maxY - full.minY) / 10000, ySpan * factor);
    const [x0, x1] = clampRange(centerX - spanX / 2, centerX + spanX / 2, full.minX, full.maxX);
    const [y0, y1] = clampRange(centerY - spanY / 2, centerY + spanY / 2, full.minY, full.maxY);
    setView({ minX: x0, maxX: x1, minY: y0, maxY: y1 }); setHoverIndex(null);
  };
  const pan = (horizontal: number, vertical: number) => {
    const [x0, x1] = clampRange(minX + horizontal * xSpan / 4, maxX + horizontal * xSpan / 4, full.minX, full.maxX);
    const [y0, y1] = clampRange(minY + vertical * ySpan / 4, maxY + vertical * ySpan / 4, full.minY, full.maxY);
    setView({ minX: x0, maxX: x1, minY: y0, maxY: y1 }); setHoverIndex(null);
  };
  const pixel = (clientX: number, clientY: number): Pixel => {
    const rect = svgRef.current!.getBoundingClientRect();
    return { x: (clientX - rect.left) * width / rect.width, y: (clientY - rect.top) * height / rect.height };
  };
  const inside = (p: Pixel) => p.x >= left && p.x <= right && p.y >= top && p.y <= bottom;
  const bounded = (p: Pixel): Pixel => ({ x: Math.max(left + 8, Math.min(right - 8, p.x)), y: Math.max(y(maxY), Math.min(y(minY), p.y)) });
  const nearest = (position: Pixel) => {
    let best: number | null = null, distance = Infinity;
    points.forEach((p, index) => { if (p.nx < minX || p.nx > maxX || p.y < minY || p.y > maxY) return; const d = (x(p.nx) - position.x) ** 2 + (y(p.y) - position.y) ** 2; if (d < distance) { distance = d; best = index; } });
    setHoverIndex(best);
  };
  const finishDrag = () => {
    if (!drag) return;
    const dx = Math.abs(drag.end.x - drag.start.x), dy = Math.abs(drag.end.y - drag.start.y);
    if (dx >= 8 || dy >= 8) {
      const invertX = (px: number) => minX + (px - left - 8) / (right - left - 16) * xSpan;
      const invertY = (py: number) => minY + ((bottom - 8 - py) / (bottom - top - 16) * 1.16 - .08) * ySpan;
      const a = bounded(drag.start), b = bounded(drag.end);
      const next = { minX: dx >= 8 ? Math.min(invertX(a.x), invertX(b.x)) : minX, maxX: dx >= 8 ? Math.max(invertX(a.x), invertX(b.x)) : maxX, minY: dy >= 8 ? Math.min(invertY(a.y), invertY(b.y)) : minY, maxY: dy >= 8 ? Math.max(invertY(a.y), invertY(b.y)) : maxY };
      if (next.maxX > next.minX && next.maxY > next.minY) setView(next);
      setHoverIndex(null);
    }
    setDrag(null);
  };
  const hovered = hoverIndex === null ? null : points[hoverIndex];
  const hoverRows = hovered ? (result.series ?? [{id:'',label:'Recorded observation',color:'#477bb0'}]).map(series=>{
    const candidates=points.filter(p=>(!result.series || p.series_id===series.id));
    const exact=!result.series ? hovered : candidates.find(p=>p.nx===hovered.nx);
    if(exact)return {series,point:exact};
    if(timeAxis)return {series,point:null};
    const before=candidates.filter(p=>p.nx<hovered.nx).at(-1),after=candidates.find(p=>p.nx>hovered.nx);
    if(!before || !after || before.segment!==after.segment)return {series,point:null};
    const point=hovered.nx-before.nx<=after.nx-hovered.nx ? before : after;
    return {series,point};
  }) : [];
  const hoverBand=hovered ? result.range_band?.points.find(p=>p.date===hovered.date) : null;
  const exactNumber = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 6 });
  const readoutX = hovered ? elapsedAxis ? `${elapsedLabel(hovered.nx)} (${exactNumber(hovered.nx)} s)` : timestampAxis ? new Date(hovered.nx).toLocaleString([], {timeZone:result.spec.timezone}) : timeAxis ? hovered.date : `${exactNumber(Number(hovered.x))} ${result.x_unit}` : '';
  const tooltipX = hovered ? Math.min(width - 245, Math.max(8, x(hovered.nx) + 12)) / width * 100 : 0;
  const tooltipY = hovered ? Math.max(8, Math.min(height - 160, y(hovered.y) - 90)) : 0;
  const zoomed = minX !== full.minX || maxX !== full.maxX || minY !== full.minY || maxY !== full.maxY;
  const geometry=useMemo(()=>(<g clipPath={`url(#${clipId})`}>{result.range_band?.points.map((band,i)=>{const nx=Date.parse(band.date+'T00:00:00Z'),next=result.range_band!.points[i+1],nextX=next?Date.parse(next.date+'T00:00:00Z'):null,previous=result.range_band!.points[i-1];if(nextX!==nx+86400000 && previous && Date.parse(previous.date+'T00:00:00Z')===nx-86400000)return null;return next && nextX===nx+86400000 ? <polygon key={`band-${i}`} points={`${x(nx)},${y(band.low)} ${x(nx)},${y(band.high)} ${x(nextX)},${y(next.high)} ${x(nextX)},${y(next.low)}`} className="chart-optimal-band"/> : <rect key={`band-${i}`} x={x(nx-43200000)} y={y(band.high)} width={x(nx+43200000)-x(nx-43200000)} height={Math.max(1,y(band.low)-y(band.high))} className="chart-optimal-band"/>;})}{result.spec.kind==='line' && segments.map((segment,i) => <polyline key={i} points={segment.map(p => `${x(p.nx)},${y(p.y)}`).join(' ')} className="chart-line" style={multiSeries ? { stroke: seriesColour(segment[0]?.series_id), strokeDasharray: seriesIndex(segment[0]?.series_id) % 2 ? '7 3' : undefined } : undefined}/>)}
    {analysis?.reference_lines.map((line,i) => <g key={`ref-${i}`}><line x1={left} x2={right} y1={y(line.value)} y2={y(line.value)} className="chart-reference"/><text x={right-4} y={y(line.value)-5} textAnchor="end">{line.label}: {number(line.value)} {result.unit}</text></g>)}
    {trend && <line x1={x(!timeAxis?Number(trend.x_start):Date.parse(trend.x_start+'T00:00:00Z'))} x2={x(!timeAxis?Number(trend.x_end):Date.parse(trend.x_end+'T00:00:00Z'))} y1={y(trend.y_start)} y2={y(trend.y_end)} className="chart-trend"><title>Least-squares trend</title></line>}
    {points.map((p,i) => <g key={i}><title>{`${elapsedAxis ? `${result.series?.find(s => s.id === p.series_id)?.label ?? p.id} · ${elapsedLabel(p.nx)}` : p.date}: ${!timeAxis ? `${number(Number(p.x))} ${result.x_unit}, ` : ''}${number(p.y)} ${result.unit} · ${p.source.replaceAll('_',' ')}`}</title>{result.spec.kind==='bar'?<rect x={x(p.nx)-Math.min(7,(right-left)/points.length/3)} y={y(p.y)} width={Math.max(1,Math.min(14,(right-left)/points.length*2/3))} height={Math.max(1,y(0)-y(p.y))} className="chart-mark"/>:<circle cx={x(p.nx)} cy={y(p.y)} r={scatter?4:points.length<100?3:1.5} className="chart-mark" style={multiSeries ? { fill: seriesColour(p.series_id) } : undefined}/>}</g>)}
    </g>),[result,points,width,height,minX,maxX,minY,maxY,clipId]);
  return <div className="plot-frame">{result.series && <ul className="chart-series-legend" aria-label="Plot legend">{result.series.map((series, index) => <li key={series.id}><span className="chart-series-swatch" style={{ borderColor: series.color ?? seriesColours[index % seriesColours.length], borderTopStyle: index % 2 ? 'dashed' : 'solid' }} aria-hidden="true"/><span>{series.label}<small>{series.started_at && <>{series.date} · {new Date(series.started_at).toLocaleTimeString([], { timeZone: result.spec.timezone, hour: '2-digit', minute: '2-digit', second: '2-digit' })} · </>}{series.count.toLocaleString()} {elapsedAxis?'samples':'days'}{series.count === 0 ? ' · no trace available' : ''}</small></span></li>)}</ul>}{!!result.range_band?.points.length && <div className="optimal-band-legend"><i/> {result.range_band.label}</div>}<div className="plot-controls" aria-label="Plot view controls"><button type="button" onClick={() => zoom(.5)}>Zoom in</button><button type="button" disabled={!zoomed} onClick={() => zoom(2)}>Zoom out</button><button type="button" disabled={!zoomed} onClick={() => { setView(null); setHoverIndex(null); }}>Reset view</button><button type="button" aria-label="Pan left" disabled={minX <= full.minX} onClick={() => pan(-1, 0)}>←</button><button type="button" aria-label="Pan right" disabled={maxX >= full.maxX} onClick={() => pan(1, 0)}>→</button><button type="button" aria-label="Pan up" disabled={maxY >= full.maxY} onClick={() => pan(0, 1)}>↑</button><button type="button" aria-label="Pan down" disabled={minY <= full.minY} onClick={() => pan(0, -1)}>↓</button><small>Drag a box to zoom. Hover or tap for recorded X/Y values.</small></div><div className="plot-interactive"><svg ref={svgRef} tabIndex={0} onPointerDown={event => { const position = pixel(event.clientX, event.clientY); if (!inside(position)) return; nearest(position); if (event.pointerType !== 'touch' && event.button === 0) { event.currentTarget.setPointerCapture(event.pointerId); setDrag({ start: position, end: position }); } }} onPointerMove={event => { const position = pixel(event.clientX, event.clientY); if (drag) setDrag({ ...drag, end: position }); else if (inside(position)) nearest(position); else setHoverIndex(null); }} onPointerUp={finishDrag} onPointerCancel={() => setDrag(null)} onPointerLeave={() => { if (!drag) setHoverIndex(null); }} onKeyDown={event => { if (event.key === '+' || event.key === '=') { event.preventDefault(); zoom(.5); } else if (event.key === '-') { event.preventDefault(); zoom(2); } else if (event.key === 'Escape' || event.key === '0') { setView(null); setHoverIndex(null); setDrag(null); } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); const visible = points.map((p, index) => ({ p, index })).filter(({ p }) => p.nx >= minX && p.nx <= maxX && p.y >= minY && p.y <= maxY).sort((a, b) => a.p.nx - b.p.nx); const current = visible.findIndex(p => p.index === hoverIndex); const next = current < 0 ? 0 : Math.max(0, Math.min(visible.length - 1, current + (event.key === 'ArrowRight' ? 1 : -1))); setHoverIndex(visible[next]?.index ?? null); } }} viewBox={`0 0 ${width} ${height}`} style={{height}} role="img" aria-label={`${result.spec.title ?? label(result.spec.metric)}. ${result.count} recorded observations. Drag to zoom; arrow keys inspect values, plus/minus zoom, zero resets.`}>
    <defs><clipPath id={clipId}><rect x={left} y={top} width={right-left} height={bottom-top}/></clipPath></defs>
    <text x={left} y="16" className="axis-label">{result.unit}</text>
    {[0,1,2,3,4].map(i => {const v=minY+(maxY-minY)*i/4; return <g key={i}><line x1={left} x2={right} y1={y(v)} y2={y(v)} className="chart-grid"/><text x={left-10} y={y(v)+4} textAnchor="end">{number(v)}</text></g>;})}
    {(minX === maxX ? [0] : [0,1,2]).map(i => <text key={i} x={minX===maxX ? x(minX) : left+(right-left)*i/2} y={bottom+22} textAnchor={minX===maxX?'middle':i===0?'start':i===2?'end':'middle'}>{tickX(minX+xSpan*i/2)}</text>)}
    <text x={(left+right)/2} y={height-11} textAnchor="middle" className="axis-label">{elapsedAxis ? `Elapsed time (${maxX >= 3600 ? 'h:mm:ss' : 'm:ss'})` : !timeAxis ? `${label(result.spec.x_metric!)} (${result.x_unit})` : timestampAxis ? `Time (${result.spec.timezone??'local'})` : 'Date / time'}</text>
    {geometry}{hovered && <g pointerEvents="none"><line x1={x(hovered.nx)} x2={x(hovered.nx)} y1={top} y2={bottom} className="plot-crosshair"/>{hoverRows.map(({series,point})=>point && <circle key={series.id} cx={x(point.nx)} cy={y(point.y)} r={5} fill={series.color ?? seriesColour(series.id)} stroke="white" strokeWidth={2}/>)}</g>}{drag && <rect x={Math.min(drag.start.x, drag.end.x)} y={Math.min(drag.start.y, drag.end.y)} width={Math.abs(drag.end.x-drag.start.x)} height={Math.abs(drag.end.y-drag.start.y)} className="plot-selection" pointerEvents="none"/>}
  </svg>{hovered && !drag && <div role="tooltip" className="plot-value-tooltip" style={{ left: `${Math.max(0, tooltipX)}%`, top: tooltipY }}><strong>X: {readoutX}</strong>{hoverRows.map(({series,point})=><span key={series.id} className="plot-hover-series"><i style={{background:series.color ?? seriesColour(series.id)}}/>{series.label}: <b>{point ? `${exactNumber(point.y)} ${result.unit}` : 'No recorded value'}</b>{point && point.nx!==hovered.nx && <small>at {elapsedLabel(point.nx)} · nearest sample</small>}</span>)}{hoverBand && <span>Optimal range: {exactNumber(hoverBand.low)}–{exactNumber(hoverBand.high)}</span>}<small>Guide shows recorded values; missing data is not interpolated.</small></div>}</div>{analysis && (result.spec.correlation || result.spec.trend_line) && <div className="plot-analysis" role="status">{analysis.pearson_r !== null && <strong>Pearson r = {analysis.pearson_r.toFixed(3)} · R² = {analysis.r_squared!.toFixed(3)}</strong>}{trend && <span>Dashed amber line: linear regression · fitted change {(trend.y_end-trend.y_start)>=0?'+':''}{(trend.y_end-trend.y_start).toFixed(2)} {result.unit}{!result.spec.correlation ? ` · R² = ${trend.r_squared.toFixed(3)}` : ''}</span>}<span>{analysis.sample_count} {!timeAxis ? 'paired observations' : 'observations; X is calendar time'}. {analysis.reason ?? 'Association does not establish causation; conditions and outliers can affect the result.'}</span></div>}</div>;
}

export default memo(InteractivePlot);
