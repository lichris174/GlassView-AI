// Two-tone split-G logo. A ~320° arc with a crossbar arm; a ghost copy offset behind;
// the primary G is split horizontally at cy+4% — top in the signature accent, bottom in a
// dimmer secondary tone. All strokes pull from --gv-* tokens so the logo follows the theme
// (near-white on dark, near-black on light). animate=true adds the notif ring.
interface GLogoProps {
  size: number;
  animate?: boolean;
}

export function GLogo({ size, animate = false }: GLogoProps) {
  const c = size / 2;
  const r = size * 0.315;
  const sw = size * 0.072;
  const openAngle = -0.22;
  const sweep = 1.78 * Math.PI;
  const startA = openAngle;
  const endA = openAngle + sweep;
  const ax1 = c + r * Math.cos(startA);
  const ay1 = c + r * Math.sin(startA);
  const ax2 = c + r * Math.cos(endA);
  const ay2 = c + r * Math.sin(endA);
  const splitY = c + size * 0.04;
  const uid = `g${size}${animate}`;
  const ghostColor = "var(--gv-sepColor)";
  const dx = size * 0.08;
  const dy = size * 0.07;
  const fgPath = `M ${ax1.toFixed(2)} ${ay1.toFixed(2)} A ${r} ${r} 0 1 1 ${ax2.toFixed(2)} ${ay2.toFixed(2)} L ${c.toFixed(2)} ${ay2.toFixed(2)}`;
  const gxPath = `M ${(ax1 + dx).toFixed(2)} ${(ay1 + dy).toFixed(2)} A ${r} ${r} 0 1 1 ${(ax2 + dx).toFixed(2)} ${(ay2 + dy).toFixed(2)} L ${(c + dx).toFixed(2)} ${(ay2 + dy).toFixed(2)}`;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} fill="none">
      <defs>
        <clipPath id={`t-${uid}`}><rect x={0} y={0} width={size} height={splitY} /></clipPath>
        <clipPath id={`b-${uid}`}><rect x={0} y={splitY} width={size} height={size} /></clipPath>
      </defs>
      <path d={gxPath} stroke={ghostColor} strokeWidth={sw} strokeLinecap="round" />
      <path d={fgPath} stroke="var(--gv-accent)" strokeWidth={sw} strokeLinecap="round" clipPath={`url(#t-${uid})`} />
      <path d={fgPath} stroke="var(--gv-textSecondary)" strokeWidth={sw} strokeLinecap="round" clipPath={`url(#b-${uid})`} />
      {animate && (
        <circle cx={c} cy={c} r={size * 0.46} stroke="var(--gv-accentBorder)" strokeWidth={size * 0.04} fill="none">
          <animate attributeName="r" values={`${size * 0.38};${size * 0.48};${size * 0.38}`} dur="1.6s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.6;0;0.6" dur="1.6s" repeatCount="indefinite" />
        </circle>
      )}
    </svg>
  );
}
