"use client";

import "@/app/charts.css";
import { chartColor } from "./ChartDataTable";
import { formatCount } from "./format";
import type { SparklineProps } from "./types";

const W = 100;
const H = 24;
const PAD = 2;

/** Small inline trend line with a text summary as its accessible name. */
export function Sparkline({ label, values, color, className }: SparklineProps) {
  const data = values.filter((value) => Number.isFinite(value));
  if (!data.some((value) => value > 0)) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const points = (data.length === 1 ? [data[0], data[0]] : data).map(
    (value, index, list) => {
      const x = (index / (list.length - 1)) * W;
      const y = H - PAD - ((value - min) / span) * (H - PAD * 2);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    },
  );
  const line = points.join(" ");
  const area = `0,${H} ${line} ${W},${H}`;
  const stroke = chartColor(color, 0);
  const summary = `${label}: from ${formatCount(data[0])} to ${formatCount(
    data[data.length - 1],
  )}, min ${formatCount(min)}, max ${formatCount(max)}`;

  return (
    <svg
      className={`chart-sparkline${className ? ` ${className}` : ""}`}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={summary}
    >
      <polygon points={area} style={{ fill: stroke, fillOpacity: 0.14 }} />
      <polyline
        points={line}
        fill="none"
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
        style={{ stroke }}
      />
    </svg>
  );
}
