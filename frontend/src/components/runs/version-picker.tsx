"use client"

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

/** Choose which version of an output to view (latest first). */
export function VersionPicker({
  versions,
  value,
  onChange,
  sources,
}: {
  versions: number
  value: number
  onChange: (version: number) => void
  sources?: Record<number, string>
}) {
  if (versions <= 1) return <span className="text-xs text-muted-foreground">Version 1</span>
  const options = Array.from({ length: versions }, (_, i) => versions - i)
  return (
    <Select value={String(value)} onValueChange={(v) => onChange(Number(v))}>
      <SelectTrigger className="h-8 w-48" aria-label="Version">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((v) => (
          <SelectItem key={v} value={String(v)}>
            Version {v}
            {v === versions ? " (latest)" : ""}
            {sources?.[v] === "human" ? " · edited" : ""}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
