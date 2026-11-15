"use client"

import { ExternalLinkIcon, FileTextIcon, GlobeIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import type { BrandResearch, BrandSource, CompetitorReport } from "@/lib/api/types"
import { formatDateTime } from "@/lib/format"
import { useOutput } from "@/lib/queries/campaigns"

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</p>
      <div className="text-sm">{children}</div>
    </div>
  )
}

const list = (items: string[]) =>
  items.length ? (
    <ul className="list-disc space-y-1 pl-5">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  ) : (
    <span className="text-muted-foreground">—</span>
  )

/** Only render real web links (backend already normalises to http/https). */
const safeHref = (url: string) => (/^https?:\/\//i.test(url) ? url : undefined)

export function ResearchView({ runId }: { runId: string }) {
  const brand = useOutput(runId, "brand_research")
  const competitors = useOutput(runId, "competitor_research")
  const research = brand.data?.content as { research: BrandResearch; sources: BrandSource[] } | undefined
  const report = competitors.data?.content as CompetitorReport | undefined

  if (brand.isPending) return <Skeleton className="h-64 rounded-xl" />

  return (
    <div className="space-y-6">
      {research && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileTextIcon className="size-4 text-primary" aria-hidden /> Brand research
            </CardTitle>
            <CardDescription>From the brand profile and its knowledge-base documents only.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <p className="text-sm">{research.research.summary}</p>
            <div className="grid gap-5 md:grid-cols-2">
              <Section label="Tone of voice">{research.research.tone_of_voice || "—"}</Section>
              <Section label="Personality">{research.research.brand_personality || "—"}</Section>
              <Section label="Target audience">{research.research.target_audience || "—"}</Section>
              <Section label="Positioning">{research.research.positioning || "—"}</Section>
              <Section label="Key messages">{list(research.research.key_messages)}</Section>
              <Section label="Prohibited claims">{list(research.research.prohibited_claims)}</Section>
            </div>
            {research.research.knowledge_gaps.length > 0 && (
              <Section label="Knowledge gaps">{list(research.research.knowledge_gaps)}</Section>
            )}
            {research.sources.some((s) => s.cited) && (
              <Section label="Cited documents">
                <ul className="space-y-2">
                  {research.sources
                    .filter((s) => s.cited)
                    .map((s) => (
                      <li key={s.source} className="rounded-md border border-border p-2">
                        <span className="font-medium">[{s.source}] {s.original_filename}</span>
                        {s.source_page != null && <span className="text-muted-foreground"> · page {s.source_page}</span>}
                        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">{s.excerpt}</p>
                      </li>
                    ))}
                </ul>
              </Section>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <GlobeIcon className="size-4 text-primary" aria-hidden /> Competitors & market
          </CardTitle>
          <CardDescription>Live web research; every finding cites a source.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {!report ? (
            <p className="text-sm text-muted-foreground">Competitor research was not run for this campaign.</p>
          ) : (
            <>
              <p className="text-sm">{report.summary}</p>
              <div className="grid gap-3 md:grid-cols-2">
                {report.competitors.map((c) => (
                  <div key={c.name} className="rounded-lg border border-border p-4">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-medium">{c.name}</p>
                      <span className="text-xs text-muted-foreground">{c.sources.join(" ")}</span>
                    </div>
                    <p className="mt-2 text-sm"><span className="text-muted-foreground">Positioning:</span> {c.positioning}</p>
                    <p className="mt-1 text-sm"><span className="text-muted-foreground">Messaging:</span> {c.messaging}</p>
                  </div>
                ))}
              </div>
              <div className="grid gap-5 md:grid-cols-2">
                <Section label="Market trends">
                  <ul className="space-y-1.5">
                    {report.market_trends.map((t) => (
                      <li key={t.trend}>
                        {t.trend} <span className="text-xs text-muted-foreground">{t.sources.join(" ")}</span>
                      </li>
                    ))}
                  </ul>
                </Section>
                <Section label="Opportunities">
                  <ul className="space-y-1.5">
                    {report.opportunities.map((o) => (
                      <li key={o.opportunity}>
                        <span className="font-medium">{o.opportunity}</span>{" "}
                        {!o.evidence_backed && <Badge variant="outline" className="ml-1">inference</Badge>}
                        <p className="text-muted-foreground">{o.rationale}</p>
                      </li>
                    ))}
                  </ul>
                </Section>
              </div>
              <Section label={`Sources (${report.sources.filter((s) => s.cited).length} cited)`}>
                <ul className="space-y-1">
                  {report.sources
                    .filter((s) => s.cited)
                    .map((s) => (
                      <li key={s.id} className="flex items-baseline gap-2">
                        <span className="w-8 shrink-0 text-xs text-muted-foreground">{s.id}</span>
                        <a
                          href={safeHref(s.url)}
                          target="_blank"
                          rel="noopener noreferrer nofollow"
                          className="min-w-0 truncate hover:text-primary"
                        >
                          {s.title} <ExternalLinkIcon className="inline size-3" aria-hidden />
                        </a>
                        <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                          {s.domain} · retrieved {formatDateTime(s.retrieved_at)}
                        </span>
                      </li>
                    ))}
                </ul>
              </Section>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
