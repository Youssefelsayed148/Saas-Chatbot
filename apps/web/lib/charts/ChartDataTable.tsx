"use client";

import { useSyncExternalStore } from "react";
import type { ChartColor, ChartDataTableProps } from "./types";

/** Palette slot (1..6) -> CSS token reference. Default slot is index + 1. */
export function chartColor(
  color: ChartColor | undefined,
  index: number,
): string {
  const slot = color ?? (((index % 6) + 1) as ChartColor);
  return `var(--chart-${slot})`;
}

const noopSubscribe = () => () => {};

/** False on the server and first render, true after hydration. */
export function useMounted(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true,
    () => false,
  );
}

const REDUCED = "(prefers-reduced-motion: reduce)";

/** Live prefers-reduced-motion flag (false on the server). */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    (notify) => {
      const query = window.matchMedia(REDUCED);
      query.addEventListener("change", notify);
      return () => query.removeEventListener("change", notify);
    },
    () => window.matchMedia(REDUCED).matches,
    () => false,
  );
}

/** Visually hidden table: the text alternative of a chart. */
export function ChartDataTable({
  caption,
  columns,
  rows,
}: ChartDataTableProps) {
  return (
    <table className="sr-only chart-sr-only">
      <caption>{caption}</caption>
      <thead>
        <tr>
          {columns.map((column, index) => (
            <th key={index} scope="col">
              {column}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, rowIndex) => (
          <tr key={rowIndex}>
            {row.map((cell, index) =>
              index === 0 ? (
                <th key={index} scope="row">
                  {cell}
                </th>
              ) : (
                <td key={index}>{cell}</td>
              ),
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
