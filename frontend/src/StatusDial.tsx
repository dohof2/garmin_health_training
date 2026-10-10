export type DialBand = { label: string; color: string; end: number };
export const fitnessBands: DialBand[] = [
  { label: 'Poor', color: '#dc545c', end: .2 },
  { label: 'Fair', color: '#e79938', end: .4 },
  { label: 'Good', color: '#39a582', end: .6 },
  { label: 'Excellent', color: '#468bd5', end: .8 },
  { label: 'Superior', color: '#9865cf', end: 1 },
];
export const readinessBands: DialBand[] = [
  { label: 'Recovery focus', color: '#dc545c', end: .5 },
  { label: 'Ready with care', color: '#e79938', end: .8 },
  { label: 'Well prepared', color: '#39a582', end: 1 },
];
const point = (fraction: number, radius: number) => {
  const angle = Math.PI * (1 - Math.max(0, Math.min(1, fraction)));
  return [140 + radius * Math.cos(angle), 135 - radius * Math.sin(angle)];
};
export default function StatusDial({ value, unit, bands, position, range, interpretation }: {
  value: string; unit: string; bands: DialBand[]; position?: number | null;
  range?: { low: number; high: number } | null; interpretation: string;
}) {
  const markers = position != null ? [position] : range ? [range.low, range.high] : [];
  return <div className="status-dial">
    <svg viewBox="0 0 280 165" role="img" aria-label={`${value} ${unit}. ${interpretation}${range ? '. Arrows mark the possible range.' : ''}`}>
      {bands.map((band, index) => {
        const start = index ? bands[index - 1].end : 0;
        const a = point(start + .006, 100), b = point(band.end - .006, 100);
        return <path key={band.label} d={`M ${a.join(' ')} A 100 100 0 0 1 ${b.join(' ')}`} fill="none" stroke={band.color} strokeWidth="13" />;
      })}
      {markers.map((fraction, index) => {
        const tip = point(fraction, 111), a = point(fraction - .025, 126), b = point(fraction + .025, 126);
        return <path key={index} className="dial-pointer" d={`M ${tip.join(' ')} L ${a.join(' ')} L ${b.join(' ')} Z`} />;
      })}
      <text x="140" y="117" textAnchor="middle" className={`status-dial-value ${value.length > 7 ? 'status-dial-value--text' : ''}`}>{value}</text>
      <text x="140" y="142" textAnchor="middle" className="status-dial-unit">{unit}</text>
    </svg>
    <p className="status-dial-interpretation">{interpretation}</p>
    <div className="dial-legend" aria-label="Status scale">{bands.map(band => <span key={band.label}><i style={{ backgroundColor: band.color }} aria-hidden="true" />{band.label}</span>)}</div>
  </div>;
}
