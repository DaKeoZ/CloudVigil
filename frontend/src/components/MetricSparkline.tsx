"use client";

import { useId } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { MetricPoint } from "@/types";

interface MetricSparklineProps {
  data: MetricPoint[];
  metric: "cpu_usage" | "ram_usage" | "disk_usage";
  color: "blue" | "violet" | "amber";
  label: string;
}

const STROKE: Record<MetricSparklineProps["color"], string> = {
  blue: "#3b82f6",
  violet: "#a855f7",
  amber: "#f59e0b",
};

/**
 * Courbe compacte (sparkline) pour fond sombre.
 * L’index temporel est unique (ms UTC) pour éviter les collisions Tremor/Recharts
 * quand plusieurs points partagent la même heure:minute locale.
 */
export function MetricSparkline({ data, metric, color, label }: MetricSparklineProps) {
  const uid = useId().replace(/:/g, "");
  const stroke = STROKE[color];
  const gradId = `spark-${metric}-${uid}`;

  const chartData = data.map((point) => {
    const t = new Date(point.timestamp).getTime();
    const v = Number(point[metric]);
    return {
      t,
      v: Number.isFinite(v) ? Math.round(v * 10) / 10 : 0,
      labelTime: new Date(point.timestamp).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
    };
  });

  if (chartData.length < 2) {
    return (
      <div className="h-14 flex items-center justify-center text-slate-700 text-xs select-none">
        En attente de données…
      </div>
    );
  }

  return (
    <div className="h-14 w-full min-w-0">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={chartData}
          margin={{ top: 2, right: 4, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} hide />
          <YAxis domain={[0, 100]} hide />
          <Tooltip
            cursor={{ stroke: "#475569", strokeWidth: 1 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const row = payload[0].payload as {
                v: number;
                labelTime: string;
              };
              return (
                <div className="rounded-md border border-slate-600 bg-slate-900 px-2 py-1.5 text-xs shadow-md">
                  <p className="text-slate-500 mb-0.5">{row.labelTime}</p>
                  <p className="font-medium text-slate-100">
                    {label} {row.v}%
                  </p>
                </div>
              );
            }}
          />
          <Area
            type="monotone"
            dataKey="v"
            stroke={stroke}
            strokeWidth={2}
            fill={`url(#${gradId})`}
            isAnimationActive={chartData.length < 80}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
