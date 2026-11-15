"use client"

import { TableIcon, BarChart3Icon } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"

export type BarRow = { label: string; value: number }

/**
 * Single-series horizontal bar chart (dataviz method):
 * - one validated hue (--chart-1), thin bars (12px <= 24px cap), 4px rounded data-end,
 *   square at the baseline;
 * - value printed at the bar tip in text color (never the series color);
 * - optional threshold reference line; recessive gridlines;
 * - every row is a hover AND keyboard-focus target bigger than the bar, with a tooltip;
 * - a table view of the same numbers; no legend (single series - the title names it).
 */
export function BarChart({
  title,
  rows,
  max,
  threshold,
  thresholdLabel,
  format = (v) => String(v),
  unitLabel,
}: {
  title: string
  rows: BarRow[]
  max: number
  threshold?: number
  thresholdLabel?: string
  format?: (value: number) => string
  unitLabel: string
}) {
  const [active, setActive] = useState<number | null>(null)
  const [asTable, setAsTable] = useState(false)
  // Bars use at most 85% of the track so the value label always fits at the tip.
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100)) * 0.85}%`
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max)

  return (
    <figure className="space-y-3">
      <div className="flex items-center justify-end">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setAsTable((t) => !t)}
          aria-pressed={asTable}
        >
          {asTable ? <BarChart3Icon /> : <TableIcon />} {asTable ? "View as chart" : "View as table"}
        </Button>
      </div>

      {asTable ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{title}</TableHead>
              <TableHead className="text-right">{unitLabel}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.label}>
                <TableCell>{row.label}</TableCell>
                <TableCell className="text-right tabular-nums">{format(row.value)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <div role="list" aria-label={title} className="relative">
          {/* label column | plot column */}
          <div className="grid grid-cols-[minmax(110px,34%)_1fr] gap-x-3">
            <div />
            <div className="relative h-5 text-[11px] text-muted-foreground">
              {threshold != null && (
                <span className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: pct(threshold) }}>
                  {thresholdLabel ?? `threshold ${format(threshold)}`}
                </span>
              )}
            </div>
            {rows.map((row, i) => (
              <div
                key={row.label}
                role="listitem"
                tabIndex={0}
                aria-label={`${row.label}: ${format(row.value)} ${unitLabel}`}
                onMouseEnter={() => setActive(i)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
                className="col-span-2 grid grid-cols-subgrid items-center rounded-md py-1.5 outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="truncate text-sm text-muted-foreground">{row.label}</span>
                <div className="relative h-5">
                  {/* recessive gridlines */}
                  {ticks.map((t) => (
                    <span key={t} className="absolute inset-y-0 w-px bg-border/60" style={{ left: pct(t) }} aria-hidden />
                  ))}
                  {threshold != null && (
                    <span
                      className="absolute inset-y-[-6px] border-l border-dashed border-foreground/50"
                      style={{ left: pct(threshold) }}
                      aria-hidden
                    />
                  )}
                  <div className="absolute inset-y-0 left-0 flex w-full items-center">
                    <div
                      className="h-3 rounded-r-[4px] transition-opacity"
                      style={{
                        width: pct(row.value),
                        backgroundColor: "var(--chart-1)",
                        opacity: active === null || active === i ? 1 : 0.45,
                      }}
                    />
                    <span className="ml-2 text-sm whitespace-nowrap tabular-nums text-foreground">{format(row.value)}</span>
                  </div>
                  {active === i && (
                    <div
                      role="tooltip"
                      className="pointer-events-none absolute bottom-full z-10 mb-1 -translate-x-1/2 rounded-md border border-border bg-popover px-2.5 py-1.5 text-xs shadow-lg"
                      style={{ left: `min(${pct(row.value)}, 85%)` }}
                    >
                      <strong className="block text-sm tabular-nums">{format(row.value)}</strong>
                      <span className="text-muted-foreground">{row.label}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div />
            <div className="relative h-4 text-[11px] text-muted-foreground" aria-hidden>
              {ticks.map((t) => (
                <span key={t} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: pct(t) }}>
                  {format(t)}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </figure>
  )
}
