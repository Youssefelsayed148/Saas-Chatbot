"use client";

import "@/app/charts.css";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import {
  chartColor,
  useMounted,
  usePrefersReducedMotion,
} from "./ChartDataTable";
import { formatCount, formatPercent } from "./format";
import type { DonutChartProps } from "./types";

/** Ring chart with optional centre text and a legend of label, value and percent. */
export function DonutChart({
  label,
  slices,
  center,
  formatValue = formatCount,
  className,
}: DonutChartProps) {
  const mounted = useMounted();
  const reduced = usePrefersReducedMotion();
  const shown = slices.filter((slice) => slice.value > 0);
  if (shown.length === 0) return null;
  const total = shown.reduce((sum, slice) => sum + slice.value, 0);
  const colors = shown.map((slice, index) => chartColor(slice.color, index));

  return (
    <figure
      className={`chart-figure chart-donut${className ? ` ${className}` : ""}`}
      aria-label={label}
      role="group"
    >
      <div className="chart-donut-ring" aria-hidden="true">
        {mounted ? (
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie
                data={shown.map((slice) => ({ ...slice }))}
                dataKey="value"
                nameKey="label"
                innerRadius="64%"
                outerRadius="100%"
                startAngle={90}
                endAngle={-270}
                stroke="var(--surface)"
                strokeWidth={2}
                isAnimationActive={!reduced}
              >
                {shown.map((slice, index) => (
                  <Cell key={slice.key} fill={colors[index]} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        ) : null}
        {center ? (
          <div className="chart-donut-center">
            <span className="chart-donut-value">{center.value}</span>
            {center.caption ? (
              <span className="chart-donut-caption">{center.caption}</span>
            ) : null}
          </div>
        ) : null}
      </div>
      <ul className="chart-legend">
        {shown.map((slice, index) => (
          <li key={slice.key} className="chart-legend-item">
            <span
              className="chart-swatch"
              style={{ background: colors[index] }}
              aria-hidden="true"
            />
            <span className="chart-legend-label">
              <bdi dir="auto">{slice.label}</bdi>
            </span>
            <bdi dir="ltr" className="chart-legend-value">
              {formatValue(slice.value)} · {formatPercent(slice.value / total)}
            </bdi>
          </li>
        ))}
      </ul>
    </figure>
  );
}
