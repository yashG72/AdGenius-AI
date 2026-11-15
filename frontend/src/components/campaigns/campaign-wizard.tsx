"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { CheckIcon, ChevronLeftIcon, ChevronRightIcon, SparklesIcon } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Controller, useForm, useWatch } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { api, unwrap } from "@/lib/api/client"
import { errorMessage } from "@/lib/api/errors"
import type { BriefFields, Campaign } from "@/lib/api/types"
import { titleCase } from "@/lib/format"
import { useBrands } from "@/lib/queries/brands"
import { useCreateCampaign, useStartRun, useUpdateCampaign } from "@/lib/queries/campaigns"
import { cn } from "@/lib/utils"

const PLATFORMS = ["instagram", "youtube", "tiktok", "facebook", "linkedin", "x", "tv", "web", "other"] as const
const FORMATS = ["9:16", "16:9", "1:1", "4:5"] as const
const FORMAT_HINT: Record<(typeof FORMATS)[number], string> = {
  "9:16": "Vertical — Reels, Shorts, TikTok",
  "16:9": "Landscape — YouTube, TV",
  "1:1": "Square — feeds",
  "4:5": "Portrait — feeds",
}

const optional = (max: number) => z.string().trim().max(max)
const schema = z.object({
  brand_id: z.string().min(1, "Choose a brand"),
  name: z.string().trim().min(1, "Name the campaign").max(300),
  objective: z.string().trim().min(1, "What should this campaign achieve?").max(4000),
  marketing_objective: optional(4000),
  product_description: optional(4000),
  target_audience: z.string().trim().min(1, "Who is it for?").max(4000),
  platform: z.enum(PLATFORMS),
  video_format: z.enum(FORMATS),
  duration_seconds: z.number().int().min(5, "At least 5 seconds").max(180, "At most 180 seconds"),
  language: z.string().trim().min(1).max(300),
  tone: optional(300),
  num_concepts: z.number().int().min(1).max(5),
  budget: optional(300),
  additional_requirements: optional(4000),
  competitor_research: z.boolean(),
  competitor_focus: optional(300),
})
type Values = z.infer<typeof schema>

const STEPS: { title: string; description: string; fields: (keyof Values)[] }[] = [
  { title: "Brand & goal", description: "What are we advertising, and why?", fields: ["brand_id", "name", "objective", "marketing_objective", "product_description"] },
  { title: "Audience & format", description: "Who sees it, where, and for how long?", fields: ["target_audience", "platform", "video_format", "duration_seconds", "language", "tone"] },
  { title: "Creative options", description: "How the agents should work.", fields: ["num_concepts", "budget", "additional_requirements", "competitor_research", "competitor_focus"] },
  { title: "Review", description: "Check the brief, then let the agents go.", fields: [] },
]

function toBrief(v: Values): BriefFields {
  const orNull = (s: string) => (s.trim() ? s.trim() : null)
  return {
    objective: v.objective,
    marketing_objective: orNull(v.marketing_objective),
    product_description: orNull(v.product_description),
    target_audience: v.target_audience,
    platform: v.platform,
    duration_seconds: v.duration_seconds,
    language: v.language,
    tone: orNull(v.tone),
    video_format: v.video_format,
    num_concepts: v.num_concepts,
    budget: orNull(v.budget),
    additional_requirements: orNull(v.additional_requirements),
    competitor_research: v.competitor_research,
    competitor_focus: orNull(v.competitor_focus),
  }
}

function fromCampaign(c: Campaign | undefined, brandId?: string): Values {
  const b = (c?.brief ?? {}) as Partial<BriefFields>
  return {
    brand_id: c?.brand_id ?? brandId ?? "",
    name: c?.name ?? "",
    objective: b.objective ?? "",
    marketing_objective: b.marketing_objective ?? "",
    product_description: b.product_description ?? "",
    target_audience: b.target_audience ?? "",
    platform: (b.platform as Values["platform"]) ?? "instagram",
    video_format: (b.video_format as Values["video_format"]) ?? "9:16",
    duration_seconds: b.duration_seconds ?? 30,
    language: b.language ?? "English",
    tone: b.tone ?? "",
    num_concepts: b.num_concepts ?? 3,
    budget: b.budget ?? "",
    additional_requirements: b.additional_requirements ?? "",
    competitor_research: b.competitor_research ?? true,
    competitor_focus: b.competitor_focus ?? "",
  }
}

function ReviewRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value === "" || value == null) return null
  return (
    <div className="grid grid-cols-3 gap-4 py-2 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="col-span-2 whitespace-pre-wrap">{value}</dd>
    </div>
  )
}

export function CampaignWizard({
  orgId,
  campaign,
  initialBrandId,
}: {
  orgId: string
  campaign?: Campaign
  initialBrandId?: string
}) {
  const router = useRouter()
  const editing = !!campaign
  const [step, setStep] = useState(0)
  const [startNow, setStartNow] = useState(true)
  const brands = useBrands(orgId)
  const create = useCreateCampaign(orgId)
  const update = useUpdateCampaign(orgId, campaign?.id ?? "")
  const start = useStartRun(orgId, campaign?.id ?? "")

  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: fromCampaign(campaign, initialBrandId) })
  const { register, control, formState } = form
  const errors = formState.errors
  const values = useWatch({ control }) as Values
  const competitorOn = values.competitor_research
  const brandName = brands.data?.items.find((b) => b.id === values.brand_id)?.name

  const next = async () => {
    if (await form.trigger(STEPS[step]!.fields)) setStep((s) => s + 1)
  }

  const submit = form.handleSubmit(async (v) => {
    try {
      if (editing && campaign) {
        await update.mutateAsync({ name: v.name, brief: toBrief(v) })
        toast.success("Brief updated — future runs will use it")
        if (startNow) {
          const run = await start.generate.mutateAsync()
          router.push(`/orgs/${orgId}/campaigns/${campaign.id}/runs/${run.id}`)
        } else {
          router.push(`/orgs/${orgId}/campaigns/${campaign.id}`)
        }
        return
      }
      const created = await create.mutateAsync({ brand_id: v.brand_id, name: v.name, brief: toBrief(v) })
      if (!startNow) {
        router.push(`/orgs/${orgId}/campaigns/${created.id}`)
        return
      }
      // Generate via the API directly: the useStartRun hook is bound to no campaign yet.
      const run = await unwrap(
        api.POST("/api/v1/campaigns/{campaign_id}/generate", { params: { path: { campaign_id: created.id } } }),
      )
      toast.success("Campaign created — the agents are on it")
      router.push(`/orgs/${orgId}/campaigns/${created.id}/runs/${run.id}`)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  })

  const busy = formState.isSubmitting

  return (
    <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
      <ol className="flex gap-2 lg:flex-col" aria-label="Steps">
        {STEPS.map((s, i) => (
          <li key={s.title}>
            <button
              type="button"
              onClick={() => i < step && setStep(i)}
              disabled={i > step}
              aria-current={i === step ? "step" : undefined}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                i === step ? "bg-accent text-foreground" : "text-muted-foreground",
                i < step && "hover:text-foreground",
              )}
            >
              <span
                className={cn(
                  "grid size-6 shrink-0 place-items-center rounded-full border text-xs",
                  i < step && "border-primary bg-primary text-primary-foreground",
                  i === step && "border-primary text-primary",
                )}
              >
                {i < step ? <CheckIcon className="size-3.5" /> : i + 1}
              </span>
              <span className="hidden sm:inline">{s.title}</span>
            </button>
          </li>
        ))}
      </ol>

      <form onSubmit={submit} noValidate>
        <Card>
          <CardHeader>
            <CardTitle>{STEPS[step]!.title}</CardTitle>
            <CardDescription>{STEPS[step]!.description}</CardDescription>
          </CardHeader>
          <CardContent>
            {step === 0 && (
              <FieldGroup>
                <Field data-invalid={!!errors.brand_id}>
                  <FieldLabel htmlFor="brand_id">Brand</FieldLabel>
                  <Controller
                    control={control}
                    name="brand_id"
                    render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange} disabled={editing}>
                        <SelectTrigger id="brand_id">
                          <SelectValue placeholder={brands.isPending ? "Loading…" : "Choose a brand"} />
                        </SelectTrigger>
                        <SelectContent>
                          {brands.data?.items.map((b) => (
                            <SelectItem key={b.id} value={b.id}>
                              {b.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                  {editing && <FieldDescription>The brand can&apos;t change after creation.</FieldDescription>}
                  <FieldError errors={[errors.brand_id]} />
                </Field>
                <Field data-invalid={!!errors.name}>
                  <FieldLabel htmlFor="name">Campaign name</FieldLabel>
                  <Input id="name" placeholder="Campus Launch" {...register("name")} />
                  <FieldError errors={[errors.name]} />
                </Field>
                <Field data-invalid={!!errors.objective}>
                  <FieldLabel htmlFor="objective">Campaign objective</FieldLabel>
                  <Input id="objective" placeholder="Brand awareness" {...register("objective")} />
                  <FieldError errors={[errors.objective]} />
                </Field>
                <Field>
                  <FieldLabel htmlFor="marketing_objective">Marketing objective (optional)</FieldLabel>
                  <Textarea id="marketing_objective" rows={2} {...register("marketing_objective")} />
                </Field>
                <Field>
                  <FieldLabel htmlFor="product_description">Product (optional)</FieldLabel>
                  <Textarea id="product_description" rows={2} placeholder="What exactly are we selling?" {...register("product_description")} />
                </Field>
              </FieldGroup>
            )}

            {step === 1 && (
              <FieldGroup>
                <Field data-invalid={!!errors.target_audience}>
                  <FieldLabel htmlFor="target_audience">Target audience</FieldLabel>
                  <Textarea id="target_audience" rows={2} placeholder="College students aged 18–25" {...register("target_audience")} />
                  <FieldError errors={[errors.target_audience]} />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field>
                    <FieldLabel htmlFor="platform">Platform</FieldLabel>
                    <Controller
                      control={control}
                      name="platform"
                      render={({ field }) => (
                        <Select value={field.value} onValueChange={field.onChange}>
                          <SelectTrigger id="platform">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {PLATFORMS.map((p) => (
                              <SelectItem key={p} value={p}>
                                {p === "tv" ? "TV" : p === "x" ? "X" : titleCase(p)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                  </Field>
                  <Field data-invalid={!!errors.duration_seconds}>
                    <FieldLabel htmlFor="duration_seconds">Duration (seconds)</FieldLabel>
                    <Input id="duration_seconds" type="number" min={5} max={180} {...register("duration_seconds", { valueAsNumber: true })} />
                    <FieldError errors={[errors.duration_seconds]} />
                  </Field>
                </div>
                <Field>
                  <FieldLabel>Video format</FieldLabel>
                  <Controller
                    control={control}
                    name="video_format"
                    render={({ field }) => (
                      <div role="radiogroup" aria-label="Video format" className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                        {FORMATS.map((f) => (
                          <button
                            key={f}
                            type="button"
                            role="radio"
                            aria-checked={field.value === f}
                            onClick={() => field.onChange(f)}
                            className={cn(
                              "rounded-lg border px-3 py-2 text-left transition-colors",
                              field.value === f ? "border-primary bg-primary/10" : "border-border hover:bg-accent",
                            )}
                          >
                            <span className="block font-medium">{f}</span>
                            <span className="block text-xs text-muted-foreground">{FORMAT_HINT[f]}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field>
                    <FieldLabel htmlFor="language">Language</FieldLabel>
                    <Input id="language" {...register("language")} />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="tone">Tone (optional)</FieldLabel>
                    <Input id="tone" placeholder="Youthful, energetic, humorous" {...register("tone")} />
                  </Field>
                </div>
              </FieldGroup>
            )}

            {step === 2 && (
              <FieldGroup>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field>
                    <FieldLabel htmlFor="num_concepts">Concepts to generate</FieldLabel>
                    <Controller
                      control={control}
                      name="num_concepts"
                      render={({ field }) => (
                        <Select value={String(field.value)} onValueChange={(v) => field.onChange(Number(v))}>
                          <SelectTrigger id="num_concepts">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {[1, 2, 3, 4, 5].map((n) => (
                              <SelectItem key={n} value={String(n)}>
                                {n} concept{n > 1 ? "s" : ""}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="budget">Budget (optional)</FieldLabel>
                    <Input id="budget" placeholder="₹5 lakh production" {...register("budget")} />
                  </Field>
                </div>
                <Field>
                  <FieldLabel htmlFor="additional_requirements">Additional requirements (optional)</FieldLabel>
                  <Textarea id="additional_requirements" rows={3} placeholder="Feature real student moments; end on the tagline." {...register("additional_requirements")} />
                </Field>
                <Field orientation="horizontal">
                  <input id="competitor_research" type="checkbox" className="size-4 accent-[var(--primary)]" {...register("competitor_research")} />
                  <FieldLabel htmlFor="competitor_research" className="font-normal">
                    Research competitors on the live web (uses web-search credits)
                  </FieldLabel>
                </Field>
                {competitorOn && (
                  <Field>
                    <FieldLabel htmlFor="competitor_focus">Competitor focus (optional)</FieldLabel>
                    <Input id="competitor_focus" placeholder="Instagram campaigns by drink brands" {...register("competitor_focus")} />
                  </Field>
                )}
              </FieldGroup>
            )}

            {step === 3 && (
              <div className="space-y-6">
                <dl className="divide-y divide-border">
                  <ReviewRow label="Brand" value={brandName} />
                  <ReviewRow label="Campaign" value={values.name} />
                  <ReviewRow label="Objective" value={values.objective} />
                  <ReviewRow label="Marketing objective" value={values.marketing_objective} />
                  <ReviewRow label="Product" value={values.product_description} />
                  <ReviewRow label="Audience" value={values.target_audience} />
                  <ReviewRow
                    label="Format"
                    value={`${titleCase(values.platform)} · ${values.video_format} · ${values.duration_seconds}s · ${values.language}`}
                  />
                  <ReviewRow label="Tone" value={values.tone} />
                  <ReviewRow label="Concepts" value={values.num_concepts} />
                  <ReviewRow label="Budget" value={values.budget} />
                  <ReviewRow label="Requirements" value={values.additional_requirements} />
                  <ReviewRow
                    label="Competitor research"
                    value={values.competitor_research ? `Yes${values.competitor_focus ? ` — ${values.competitor_focus}` : ""}` : "No"}
                  />
                </dl>
                <Field orientation="horizontal">
                  <input id="start_now" type="checkbox" checked={startNow} onChange={(e) => setStartNow(e.target.checked)} className="size-4 accent-[var(--primary)]" />
                  <FieldLabel htmlFor="start_now" className="font-normal">
                    Start generating right away
                  </FieldLabel>
                </Field>
              </div>
            )}

            <div className="mt-8 flex justify-between">
              <Button type="button" variant="ghost" onClick={() => setStep((s) => s - 1)} disabled={step === 0 || busy}>
                <ChevronLeftIcon /> Back
              </Button>
              {step < STEPS.length - 1 ? (
                <Button type="button" onClick={next}>
                  Continue <ChevronRightIcon />
                </Button>
              ) : (
                <Button type="submit" disabled={busy}>
                  <SparklesIcon />
                  {busy ? "Working…" : startNow ? (editing ? "Save & generate" : "Create & generate") : editing ? "Save brief" : "Create campaign"}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </form>
    </div>
  )
}
