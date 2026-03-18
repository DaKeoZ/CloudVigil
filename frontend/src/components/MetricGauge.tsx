/**
 * Jauge semi-circulaire en SVG pur.
 *
 * Géométrie :
 *   - Centre (cx, cy) = (50, 52)
 *   - Rayon = 38
 *   - L'arc part du point gauche (-180°) et va vers le point droit (0°)
 *     en passant par le haut du demi-cercle.
 *   - Le "remplissage" correspond à la portion [0, value/100] de ce demi-cercle.
 *
 * Formule endpoint (angle mesuré depuis la droite, sens trigonométrique) :
 *   angle = (1 - value/100) * π
 *   endX  = cx + r * cos(angle)
 *   endY  = cy - r * sin(angle)   ← y flippé dans le repère SVG
 */

interface MetricGaugeProps {
  value: number;  // 0 – 100
  label: string;
  baseColor: string; // couleur hex par défaut
}

export function MetricGauge({ value, label, baseColor }: MetricGaugeProps) {
  const r  = 38;
  const cx = 50;
  const cy = 52;

  const safe  = Math.min(100, Math.max(0, value));
  const angle = (1 - safe / 100) * Math.PI;
  const endX  = (cx + r * Math.cos(angle)).toFixed(3);
  const endY  = (cy - r * Math.sin(angle)).toFixed(3);

  // Couleur dynamique selon le seuil de charge
  const color =
    safe >= 90 ? "#ef4444"   // red-500
    : safe >= 75 ? "#f97316" // orange-500
    : baseColor;

  const trackPath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 0 ${cx + r} ${cy}`;
  const valuePath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 0 ${endX} ${endY}`;

  return (
    <div className="flex flex-col items-center w-full">
      <svg viewBox="0 0 100 68" className="w-full max-w-[108px]" aria-label={`${label}: ${Math.round(safe)}%`}>
        {/* Fond de piste */}
        <path d={trackPath} fill="none" stroke="#1e293b" strokeWidth="9" strokeLinecap="round" />

        {/* Arc rempli */}
        {safe > 0.5 && (
          <path
            d={valuePath}
            fill="none"
            stroke={color}
            strokeWidth="9"
            strokeLinecap="round"
            style={{ transition: "d 0.6s ease, stroke 0.4s ease" }}
          />
        )}

        {/* Valeur numérique */}
        <text
          x={cx}
          y={cy - 2}
          textAnchor="middle"
          fill="white"
          fontSize="14"
          fontWeight="700"
          fontFamily="system-ui, sans-serif"
        >
          {Math.round(safe)}%
        </text>

        {/* Label */}
        <text
          x={cx}
          y={cy + 12}
          textAnchor="middle"
          fill="#64748b"
          fontSize="9"
          fontFamily="system-ui, sans-serif"
        >
          {label}
        </text>
      </svg>
    </div>
  );
}
