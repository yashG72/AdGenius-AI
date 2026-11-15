const dateTime = new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short" })
const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" })

export function formatDateTime(value: string | null | undefined): string {
  return value ? dateTime.format(new Date(value)) : "—"
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return "—"
  const seconds = Math.round((new Date(value).getTime() - Date.now()) / 1000)
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ]
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit)
  }
  return "just now"
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

export function formatDuration(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`
}

export function formatPercent(ratio: number | null | undefined): string {
  return ratio == null ? "—" : `${Math.round(ratio * 100)}%`
}

export function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

export function initials(name: string | undefined): string {
  return (name ?? "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]!.toUpperCase())
    .join("")
}
