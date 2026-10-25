import type { ReactNode } from "react";

/** Chart contract (B4). All colours come from CSS tokens: a palette slot maps to
 * var(--chart-N). Meaning is never colour-only: every chart has a legend or
 * direct labels with values, and renders a visually hidden data table (see
 * ChartDataTable) as its text alternative. Components return null when they
 * have no positive data, so a page can also hide the surrounding Card with
 * hasChartData() from ./format. All client components. prefers-reduced-motion
 * turns animation off. Logical CSS properties only (RTL-safe). */

/** Palette slot 1..6 -> var(--chart-1..6). Default: assigned in series order. */
export type ChartColor = 1 | 2 | 3 | 4 | 5 | 6;

export type TrendSeries = {
  /** Key of the numeric field in each data row. */
  key: string;
  /** Legend, tooltip and table header text. */
  label: string;
  color?: ChartColor;
};

export type TrendChartProps = {
  /** Accessible name of the figure and the table caption. Required. */
  label: string;
  /** One row per x value, e.g. { day: "2026-10-05", conversations: 4 }. */
  data: ReadonlyArray<Record<string, string | number>>;
  /** Field of the x value in each row (ISO dates are shown as "Oct 5"). */
  xKey: string;
  series: ReadonlyArray<TrendSeries>;
  /** "area" (default, soft fill under the line) or "line". */
  variant?: "area" | "line";
  /** Plot height in px; width is always 100% of the parent (ResponsiveContainer). */
  height?: number;
  formatValue?: (value: number) => string;
  className?: string;
};

export type DonutSlice = {
  key: string;
  label: string;
  value: number;
  color?: ChartColor;
};

export type DonutChartProps = {
  label: string;
  /** Zero-value slices are dropped from the ring and the legend. */
  slices: ReadonlyArray<DonutSlice>;
  /** Text in the hole, e.g. total and a caption. */
  center?: { value: ReactNode; caption?: string };
  /** Legend shows label, value and percent of total. */
  formatValue?: (value: number) => string;
  className?: string;
};

export type BarItem = {
  key: string;
  /** User text may be Arabic: rendered in <bdi dir="auto">. */
  label: string;
  value: number;
  /** Small secondary text after the value, e.g. "last asked Oct 5". */
  hint?: string;
  color?: ChartColor;
};

export type BarListProps = {
  label: string;
  /** Rendered in the given order (callers sort); bars scale to the largest value or `max`. */
  items: ReadonlyArray<BarItem>;
  max?: number;
  /** Prefix a rank number (1., 2., ...) for ranked lists. */
  ranked?: boolean;
  formatValue?: (value: number) => string;
  className?: string;
};

export type StackedSegment = {
  key: string;
  label: string;
  value: number;
  color?: ChartColor;
};

/** Single horizontal bar split into segments (e.g. sentiment), with a legend of label, value and percent. */
export type StackedBarProps = {
  label: string;
  segments: ReadonlyArray<StackedSegment>;
  formatValue?: (value: number) => string;
  className?: string;
};

export type SparklineProps = {
  /** Accessible name; also gets a text summary (first, last, min, max). */
  label: string;
  values: ReadonlyArray<number>;
  color?: ChartColor;
  className?: string;
};

export type ChartDataTableProps = {
  caption: string;
  /** Column headers; the first column is the row header. */
  columns: ReadonlyArray<string>;
  rows: ReadonlyArray<ReadonlyArray<string | number>>;
};
