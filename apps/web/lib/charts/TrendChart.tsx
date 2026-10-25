"use client";

import "@/app/charts.css";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ChartDataTable,
  chartColor,
  useMounted,
  usePrefersReducedMotion,
} from "./ChartDataTable";
import { formatCount, formatDay } from "./format";
import type { TrendChartProps } from "./types";

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const AXIS_TICK = { fill: "var(--chart-axis)", fontSize: 12 };

type TipProps = {
  active?: boolean;
  label?: string | number;
  payload?: ReadonlyArray<{ dataKey?: unknown; value?: unknown }>;
};

/** Time-series line/area chart (ISO-day x axis, integer y ticks) with legend for 2+ series. */
export function TrendChart({
  label,
  data,
  xKey,
  series,
  variant = "area",
  height = 240,
  formatValue = formatCount,
  className,
}: TrendChartProps) {
  const mounted = useMounted();
  const reduced = usePrefersReducedMotion();
  const hasData = data.some((row) =>
    series.some((s) => Number(row[s.key]) > 0),
  );
  if (!hasData) return null;

  const formatX = (value: string | number) =>
    typeof value === "string" && ISO_DAY.test(value)
      ? formatDay(value)
      : String(value);
  const colors = series.map((s, index) => chartColor(s.color, index));
  const rows = data.map((row) => ({ ...row }));
  const common = {
    data: rows,
    accessibilityLayer: true,
    margin: { top: 8, right: 8, bottom: 0, left: 0 },
  };

  const axes = [
    <CartesianGrid
      key="grid"
      vertical={false}
      stroke="var(--chart-grid)"
      strokeWidth={1}
    />,
    <XAxis
      key="x"
      dataKey={xKey}
      tickFormatter={formatX}
      tick={AXIS_TICK}
      tickLine={false}
      axisLine={false}
      interval="preserveStartEnd"
      minTickGap={24}
      tickMargin={8}
    />,
    <YAxis
      key="y"
      allowDecimals={false}
      tick={AXIS_TICK}
      tickLine={false}
      axisLine={false}
      width={40}
      tickFormatter={(value: number) => formatValue(value)}
    />,
    <Tooltip
      key="tip"
      cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1 }}
      isAnimationActive={false}
      content={(props: TipProps) =>
        props.active && props.payload?.length ? (
          <div className="chart-tooltip">
            <div className="chart-tooltip-title">
              {formatX(props.label ?? "")}
            </div>
            {series.map((s, index) => {
              const entry = props.payload?.find((p) => p.dataKey === s.key);
              if (!entry) return null;
              return (
                <div key={s.key} className="chart-tooltip-row">
                  <span
                    className="chart-swatch"
                    style={{ background: colors[index] }}
                    aria-hidden="true"
                  />
                  <span className="chart-tooltip-label">{s.label}</span>
                  <bdi dir="ltr" className="chart-tooltip-value">
                    {formatValue(Number(entry.value))}
                  </bdi>
                </div>
              );
            })}
          </div>
        ) : null
      }
    />,
  ];

  const activeDot = (index: number) => ({
    r: 4,
    stroke: "var(--surface)",
    strokeWidth: 2,
    fill: colors[index],
  });

  return (
    <figure
      className={`chart-figure${className ? ` ${className}` : ""}`}
      aria-label={label}
      role="group"
    >
      <div
        className="chart-plot"
        style={{ minBlockSize: height }}
        dir="ltr"
        aria-hidden="true"
      >
        {mounted ? (
          <ResponsiveContainer width="100%" height={height}>
            {variant === "area" ? (
              <AreaChart {...common}>
                {axes}
                {series.map((s, index) => (
                  <Area
                    key={s.key}
                    dataKey={s.key}
                    type="monotone"
                    stroke={colors[index]}
                    strokeWidth={2}
                    fill={colors[index]}
                    fillOpacity={0.14}
                    dot={false}
                    activeDot={activeDot(index)}
                    isAnimationActive={!reduced}
                  />
                ))}
              </AreaChart>
            ) : (
              <LineChart {...common}>
                {axes}
                {series.map((s, index) => (
                  <Line
                    key={s.key}
                    dataKey={s.key}
                    type="monotone"
                    stroke={colors[index]}
                    strokeWidth={2}
                    dot={false}
                    activeDot={activeDot(index)}
                    isAnimationActive={!reduced}
                  />
                ))}
              </LineChart>
            )}
          </ResponsiveContainer>
        ) : null}
      </div>
      {series.length >= 2 ? (
        <ul className="chart-legend">
          {series.map((s, index) => (
            <li key={s.key} className="chart-legend-item">
              <span
                className="chart-swatch"
                style={{ background: colors[index] }}
                aria-hidden="true"
              />
              <span className="chart-legend-label">{s.label}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <ChartDataTable
        caption={label}
        columns={[xKey, ...series.map((s) => s.label)]}
        rows={data.map((row) => [
          formatX(row[xKey]),
          ...series.map((s) => formatValue(Number(row[s.key]) || 0)),
        ])}
      />
    </figure>
  );
}
