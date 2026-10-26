"use client";

import "@/app/charts.css";
import { chartColor } from "./ChartDataTable";
import { formatCount, formatPercent } from "./format";
import type { StackedBarProps } from "./types";

/** One horizontal bar split into proportional segments, with a label/value/percent legend. */
export function StackedBar({
  label,
  segments,
  formatValue = formatCount,
  className,
}: StackedBarProps) {
  const shown = segments.filter((segment) => segment.value > 0);
  if (shown.length === 0) return null;
  const total = shown.reduce((sum, segment) => sum + segment.value, 0);

  return (
    <figure
      className={`chart-figure${className ? ` ${className}` : ""}`}
      aria-label={label}
      role="group"
    >
      <div className="chart-stacked" aria-hidden="true">
        {shown.map((segment, index) => (
          <span
            key={segment.key}
            className="chart-stacked-seg"
            style={{
              flexGrow: segment.value,
              background: chartColor(segment.color, index),
            }}
          />
        ))}
      </div>
      <ul className="chart-legend">
        {shown.map((segment, index) => (
          <li key={segment.key} className="chart-legend-item">
            <span
              className="chart-swatch"
              style={{ background: chartColor(segment.color, index) }}
              aria-hidden="true"
            />
            <span className="chart-legend-label">
              <bdi dir="auto">{segment.label}</bdi>
            </span>
            <bdi dir="ltr" className="chart-legend-value">
              {formatValue(segment.value)} ·{" "}
              {formatPercent(segment.value / total)}
            </bdi>
          </li>
        ))}
      </ul>
    </figure>
  );
}
