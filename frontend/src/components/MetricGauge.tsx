/**
 * Jauge semi-circulaire — arc SVG + pourcentage + libellé empilés et centrés.
 * Largeur fixe pour un alignement net en grille 3 colonnes.
 */

interface MetricGaugeProps {
  value: number; // 0 – 100
  label: string;
  baseColor: string;
}

export function MetricGauge({ value, label, baseColor }: MetricGaugeProps) {
  const r = 34;
  const cx = 50;
  const cy = 44;

  const safe = Math.min(100, Math.max(0, value));
  const angle = (1 - safe / 100) * Math.PI;
  const endX = (cx + r * Math.cos(angle)).toFixed(3);
  const endY = (cy - r * Math.sin(angle)).toFixed(3);

  const color =
    safe >= 90 ? "#ef4444"
    : safe >= 75 ? "#f97316"
    : baseColor;

  const trackPath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 0 ${cx + r} ${cy}`;
  const valuePath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 0 ${endX} ${endY}`;

  return (
    <div className="flex w-[5.5rem] flex-col items-center justify-start sm:w-[6rem]">
      <svg
        viewBox="0 0 100 48"
        className="h-[3rem] w-full shrink-0"
        fill="none"
        preserveAspectRatio="xMidYMid meet"
        aria-hidden
      >
        <path
          d={trackPath}
          stroke="#1e293b"
          strokeWidth="7"
          strokeLinecap="round"
        />
        {safe > 0.5 && (
          <path
            d={valuePath}
            fill="none"
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
            style={{ transition: "d 0.6s ease, stroke 0.4s ease" }}
          />
        )}
      </svg>
      <p
        className="text-center text-[0.95rem] font-bold tabular-nums leading-none text-slate-100 sm:text-base -mt-1"
        aria-label={`${label}: ${Math.round(safe)} pour cent`}
      >
        {Math.round(safe)}%
      </p>
      <p className="mt-1 text-center text-[10px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </p>
    </div>
  );
}
