/**
 * Jauge semi-circulaire : tout dans un seul SVG (viewBox fixe) pour éviter
 * tout décalage entre l’arc, le pourcentage et le libellé.
 */

interface MetricGaugeProps {
  value: number; // 0 – 100
  label: string;
  baseColor: string;
}

export function MetricGauge({ value, label, baseColor }: MetricGaugeProps) {
  const r = 32;
  const cx = 50;
  const cy = 56;

  const safe = Math.min(100, Math.max(0, value));
  const angle = (1 - safe / 100) * Math.PI;
  const endX = (cx + r * Math.cos(angle)).toFixed(2);
  const endY = (cy - r * Math.sin(angle)).toFixed(2);

  const color =
    safe >= 90 ? "#ef4444"
    : safe >= 75 ? "#f97316"
    : baseColor;

  /* sweep=1 : demi-cercle SUPÉRIEUR (gauche → droite en passant par le haut).
     sweep=0 tracerait le demi-cercle inférieur — d’où les arcs « décollés ». */
  const trackPath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
  const valuePath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${endX} ${endY}`;

  return (
    <div className="flex w-[6.25rem] shrink-0 flex-col items-center sm:w-[6.75rem]">
      <svg
        viewBox="0 0 100 78"
        className="block h-[4.75rem] w-full"
        fill="none"
        role="img"
        aria-label={`${label}: ${Math.round(safe)} pour cent`}
      >
        <path
          d={trackPath}
          stroke="#1e293b"
          strokeWidth="6"
          strokeLinecap="round"
        />
        {safe > 0.01 && (
          <path
            d={valuePath}
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeLinecap="round"
            style={{ transition: "d 0.45s ease, stroke 0.35s ease" }}
          />
        )}
        {safe <= 0.01 && (
          <circle cx={cx - r} cy={cy} r={3} fill={baseColor} opacity={0.45} />
        )}
        <text
          x={cx}
          y={cy - 6}
          textAnchor="middle"
          fill="#f1f5f9"
          fontSize="15"
          fontWeight="700"
          fontFamily="ui-sans-serif, system-ui, sans-serif"
          className="tabular-nums"
        >
          {Math.round(safe)}%
        </text>
        <text
          x={cx}
          y={72}
          textAnchor="middle"
          fill="#64748b"
          fontSize="9"
          fontWeight="600"
          fontFamily="ui-sans-serif, system-ui, sans-serif"
          letterSpacing="0.06em"
        >
          {label.toUpperCase()}
        </text>
      </svg>
    </div>
  );
}
