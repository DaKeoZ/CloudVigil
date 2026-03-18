"use client";

import { AreaChart } from "@tremor/react";
import type { MetricPoint } from "@/types";

interface MetricSparklineProps {
  data: MetricPoint[];
  metric: "cpu_usage" | "ram_usage" | "disk_usage";
  /** Doit être une couleur Tremor : "blue" | "violet" | "amber" */
  color: "blue" | "violet" | "amber";
  label: string;
}

/**
 * Mini-graphique de série temporelle (sparkline) via Tremor AreaChart.
 * Axes, légende et grille masqués pour un rendu compact dans les cartes.
 */
export function MetricSparkline({ data, metric, color, label }: MetricSparklineProps) {
  const chartData = data.map((point) => ({
    time: new Date(point.timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
    [label]: parseFloat(point[metric].toFixed(1)),
  }));

  if (chartData.length < 2) {
    return (
      <div className="h-14 flex items-center justify-center text-slate-700 text-xs select-none">
        En attente de données…
      </div>
    );
  }

  return (
    <AreaChart
      className="h-14"
      data={chartData}
      index="time"
      categories={[label]}
      colors={[color]}
      showXAxis={false}
      showYAxis={false}
      showLegend={false}
      showGridLines={false}
      curveType="monotone"
      minValue={0}
      maxValue={100}
      // Transparence du fond pour s'intégrer dans la carte sombre
      style={{ background: "transparent" }}
    />
  );
}
