"use client";

import "@/app/charts.css";
import { chartColor } from "./ChartDataTable";
import { formatCount } from "./format";
import type { BarListProps } from "./types";

/** Ranked or plain list of labelled values with a thin proportional bar under each row. */
export function BarList({
  label,
  items,
  max,
  ranked = false,
  formatValue = formatCount,
  className,
}: BarListProps) {
  if (!items.some((item) => item.value > 0)) return null;

  const scale = max && max > 0 ? max : Math.max(...items.map((i) => i.value));
  const List = ranked ? "ol" : "ul";

  return (
    <figure
      className={`chart-figure${className ? ` ${className}` : ""}`}
      aria-label={label}
      role="group"
    >
      <List className="chart-barlist">
        {items.map((item, index) => {
          const pct = Math.min(100, Math.max(0, (item.value / scale) * 100));
          return (
            <li key={item.key} className="chart-bar-row">
              <div className="chart-bar-head">
                {ranked ? (
                  <bdi dir="ltr" className="chart-bar-rank">
                    {index + 1}.
                  </bdi>
                ) : null}
                <span className="chart-bar-label" title={item.label}>
                  <bdi dir="auto">{item.label}</bdi>
                </span>
                <span className="chart-bar-value">
                  <bdi dir="ltr">{formatValue(item.value)}</bdi>
                  {item.hint ? (
                    <span className="chart-bar-hint"> {item.hint}</span>
                  ) : null}
                </span>
              </div>
              <div className="chart-bar-track" aria-hidden="true">
                <div
                  className="chart-bar-fill"
                  style={{
                    inlineSize: `${pct}%`,
                    background: chartColor(item.color, 0),
                  }}
                />
              </div>
            </li>
          );
        })}
      </List>
    </figure>
  );
}
