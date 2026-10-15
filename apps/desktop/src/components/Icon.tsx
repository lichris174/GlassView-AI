// Single-path stroked icon, ported from the mockup's Icon component.
interface IconProps {
  d: string;
  size?: number;
  stroke?: string;
  sw?: number;
  fill?: string;
}

export function Icon({ d, size = 15, stroke = "currentColor", sw = 1.5, fill = "none" }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill={fill}>
      <path
        d={d}
        stroke={stroke}
        strokeWidth={sw}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill={fill}
      />
    </svg>
  );
}
