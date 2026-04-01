"use client";

import { useId, useLayoutEffect, useRef, useState } from "react";
import {
  Area,
  AreaChart,
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

const CHART_H = 56;

/**
 * Sparkline pour fond sombre.
 * - Abscisse = index (0,1,…) : évite les bugs d’échelle Recharts avec de gros timestamps.
 * - Largeur mesurée au layout (ResizeObserver) : évite ResponsiveContainer à 0 px dans les flex.
 */
export function MetricSparkline({ data, metric, color, label }: MetricSparklineProps) {
  const uid = useId().replace(/:/g, "");
  const stroke = STROKE[color];
  const gradId = `spark-${metric}-${uid}`;
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useLayoutEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => {
      const w = Math.floor(el.getBoundingClientRect().width);
      if (w > 0) setWidth(w);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  let chartData = data.map((point, idx) => {
    const v = Number(point[metric]);
    return {
      idx,
      v: Number.isFinite(v) ? Math.round(v * 10) / 10 : 0,
      labelTime: new Date(point.timestamp).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
    };
  });

  /* Un seul point Influx : dupliquer pour que Recharts trace une ligne horizontale */
  if (chartData.length === 1) {
    chartData = [chartData[0], { ...chartData[0], idx: 1 }];
  }

  if (chartData.length === 0) {
    return (
      <div className="h-14 flex items-center justify-center text-slate-700 text-xs select-none">
        En attente de données…
      </div>
    );
  }

  return (
    <div
      ref={wrapRef}
      className="h-14 w-full min-h-[3.5rem] min-w-[8rem] shrink-0"
    >
      {width > 0 ? (
        <AreaChart
          width={width}
          height={CHART_H}
          data={chartData}
          margin={{ top: 4, right: 6, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.4} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <XAxis dataKey="idx" type="category" hide allowDuplicatedCategory />
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
            connectNulls
          />
        </AreaChart>
      ) : (
        <div
          className="h-full w-full rounded-md bg-slate-900/40"
          aria-hidden
        />
      )}
    </div>
  );
}
