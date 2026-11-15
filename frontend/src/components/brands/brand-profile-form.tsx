"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { PlusIcon, Trash2Icon } from "lucide-react"
import { useEffect } from "react"
import { useFieldArray, useForm, useWatch, type Control, type UseFormRegister } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { errorMessage } from "@/lib/api/errors"
import type { Brand, BrandUpdate } from "@/lib/api/types"
import { useUpdateBrand } from "@/lib/queries/brands"

// ---------- form schema (mirrors the backend's validation) ----------

const optionalUrl = z.union([z.literal(""), z.url("Enter a full URL, e.g. https://…")])
const text = (max: number) => z.string().trim().max(max)

const schema = z.object({
  name: z.string().trim().min(1, "Name is required").max(255),
  industry: text(100),
  website: optionalUrl,
  description: text(10_000),
  product_information: text(10_000),
  target_audience: text(10_000),
  brand_personality: text(10_000),
  brand_voice: text(10_000),
  positioning: text(10_000),
  messaging: text(10_000),
  brand_colors: z
    .array(
      z.object({
        name: z.string().trim().min(1, "Name the colour").max(50),
        hex: z.string().regex(/^#[0-9A-Fa-f]{6}$/, "Use #RRGGBB"),
      }),
    )
    .max(20),
  // useFieldArray needs objects, so plain string lists are stored as {value}.
  marketing_objectives: z.array(z.object({ value: z.string().trim().min(1, "Empty").max(500) })).max(50),
  content_restrictions: z.array(z.object({ value: z.string().trim().min(1, "Empty").max(500) })).max(50),
  competitors: z
    .array(
      z.object({
        name: z.string().trim().min(1, "Name is required").max(255),
        website: optionalUrl,
        notes: text(2000),
      }),
    )
    .max(30),
  social_links: z
    .array(z.object({ platform: z.string().trim().min(1, "Platform").max(50), url: z.url("Enter a URL") }))
    .max(20),
})
type Values = z.infer<typeof schema>

function toForm(b: Brand): Values {
  return {
    name: b.name,
    industry: b.industry ?? "",
    website: b.website ?? "",
    description: b.description ?? "",
    product_information: b.product_information ?? "",
    target_audience: b.target_audience ?? "",
    brand_personality: b.brand_personality ?? "",
    brand_voice: b.brand_voice ?? "",
    positioning: b.positioning ?? "",
    messaging: b.messaging ?? "",
    brand_colors: b.brand_colors.map((c) => ({ name: c.name, hex: c.hex })),
    marketing_objectives: b.marketing_objectives.map((value) => ({ value })),
    content_restrictions: b.content_restrictions.map((value) => ({ value })),
    competitors: b.competitors.map((c) => ({ name: c.name, website: c.website ?? "", notes: c.notes ?? "" })),
    social_links: b.social_links.map((s) => ({ platform: s.platform, url: s.url })),
  }
}

const orNull = (value: string) => (value.trim() ? value.trim() : null)

function toApi(v: Values): BrandUpdate {
  return {
    name: v.name,
    industry: orNull(v.industry),
    website: orNull(v.website),
    description: orNull(v.description),
    product_information: orNull(v.product_information),
    target_audience: orNull(v.target_audience),
    brand_personality: orNull(v.brand_personality),
    brand_voice: orNull(v.brand_voice),
    positioning: orNull(v.positioning),
    messaging: orNull(v.messaging),
    brand_colors: v.brand_colors,
    marketing_objectives: v.marketing_objectives.map((o) => o.value),
    content_restrictions: v.content_restrictions.map((o) => o.value),
    competitors: v.competitors.map((c) => ({ name: c.name, website: orNull(c.website), notes: orNull(c.notes) })),
    social_links: v.social_links,
  }
}

// ---------- small building blocks ----------

function TextField({
  label,
  name,
  register,
  error,
  multiline,
  placeholder,
  description,
}: {
  label: string
  name: keyof Values
  register: UseFormRegister<Values>
  error?: { message?: string }
  multiline?: boolean
  placeholder?: string
  description?: string
}) {
  const id = `brand-${name}`
  return (
    <Field data-invalid={!!error}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      {multiline ? (
        <Textarea id={id} rows={3} placeholder={placeholder} {...register(name)} />
      ) : (
        <Input id={id} placeholder={placeholder} {...register(name)} />
      )}
      {description && <FieldDescription>{description}</FieldDescription>}
      <FieldError errors={[error]} />
    </Field>
  )
}

function StringList({
  control,
  register,
  name,
  placeholder,
  addLabel,
}: {
  control: Control<Values>
  register: UseFormRegister<Values>
  name: "marketing_objectives" | "content_restrictions"
  placeholder: string
  addLabel: string
}) {
  const { fields, append, remove } = useFieldArray({ control, name })
  return (
    <div className="space-y-2">
      {fields.map((field, index) => (
        <div key={field.id} className="flex gap-2">
          <Input placeholder={placeholder} {...register(`${name}.${index}.value`)} aria-label={`${addLabel} ${index + 1}`} />
          <Button type="button" variant="ghost" size="icon" onClick={() => remove(index)} aria-label="Remove">
            <Trash2Icon />
          </Button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={() => append({ value: "" })}>
        <PlusIcon /> {addLabel}
      </Button>
    </div>
  )
}

// ---------- the form ----------

export function BrandProfileForm({ orgId, brand }: { orgId: string; brand: Brand }) {
  const update = useUpdateBrand(orgId, brand.id)
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: toForm(brand) })
  const { register, control, formState } = form
  // Subscribe only to colour values (for the live swatches) instead of calling watch().
  const colorValues = useWatch({ control, name: "brand_colors" })
  const errors = formState.errors

  // When fresh data arrives (e.g. after saving), make it the new "clean" state.
  useEffect(() => form.reset(toForm(brand)), [brand, form])

  const colors = useFieldArray({ control, name: "brand_colors" })
  const competitors = useFieldArray({ control, name: "competitors" })
  const socials = useFieldArray({ control, name: "social_links" })

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await update.mutateAsync(toApi(values))
      toast.success("Brand profile saved")
    } catch (e) {
      toast.error(errorMessage(e))
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Identity</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldGroup className="grid gap-4 md:grid-cols-2">
            <TextField label="Brand name" name="name" register={register} error={errors.name} />
            <TextField label="Industry" name="industry" register={register} error={errors.industry} />
            <TextField
              label="Website"
              name="website"
              register={register}
              error={errors.website}
              placeholder="https://"
            />
            <div className="md:col-span-2">
              <TextField label="Description" name="description" register={register} error={errors.description} multiline />
            </div>
          </FieldGroup>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Strategy</CardTitle>
          <CardDescription>What the agents should know before writing a single word.</CardDescription>
        </CardHeader>
        <CardContent>
          <FieldGroup className="grid gap-4 md:grid-cols-2">
            <TextField label="Products" name="product_information" register={register} error={errors.product_information} multiline />
            <TextField label="Target audience" name="target_audience" register={register} error={errors.target_audience} multiline />
            <TextField label="Brand personality" name="brand_personality" register={register} error={errors.brand_personality} multiline />
            <TextField label="Brand voice" name="brand_voice" register={register} error={errors.brand_voice} multiline />
            <TextField label="Positioning" name="positioning" register={register} error={errors.positioning} multiline />
            <TextField label="Messaging" name="messaging" register={register} error={errors.messaging} multiline />
          </FieldGroup>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Brand colours</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {colors.fields.map((field, index) => {
              const hex = colorValues?.[index]?.hex ?? ""
              const error = errors.brand_colors?.[index]
              return (
                <div key={field.id} className="flex items-start gap-2">
                  <span
                    className="mt-1 size-7 shrink-0 rounded-md border border-border"
                    style={{ backgroundColor: /^#[0-9A-Fa-f]{6}$/.test(hex) ? hex : "transparent" }}
                    aria-hidden
                  />
                  <div className="flex-1">
                    <Input placeholder="Name" {...register(`brand_colors.${index}.name`)} aria-label="Colour name" />
                    <FieldError errors={[error?.name]} />
                  </div>
                  <div className="w-32">
                    <Input placeholder="#FFB300" {...register(`brand_colors.${index}.hex`)} aria-label="Hex" />
                    <FieldError errors={[error?.hex]} />
                  </div>
                  <Button type="button" variant="ghost" size="icon" onClick={() => colors.remove(index)} aria-label="Remove colour">
                    <Trash2Icon />
                  </Button>
                </div>
              )
            })}
            <Button type="button" variant="outline" size="sm" onClick={() => colors.append({ name: "", hex: "#" })}>
              <PlusIcon /> Add colour
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Content restrictions</CardTitle>
            <CardDescription>
              Claims and wording that must never appear. The Critic agent fails any campaign that breaks
              them — quote exact words, e.g. Never say &apos;healthy&apos;.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <StringList
              control={control}
              register={register}
              name="content_restrictions"
              placeholder="Never make health claims"
              addLabel="Add restriction"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Marketing objectives</CardTitle>
          </CardHeader>
          <CardContent>
            <StringList
              control={control}
              register={register}
              name="marketing_objectives"
              placeholder="Grow awareness among students"
              addLabel="Add objective"
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Social links</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {socials.fields.map((field, index) => (
              <div key={field.id} className="flex items-start gap-2">
                <div className="w-36">
                  <Input placeholder="instagram" {...register(`social_links.${index}.platform`)} aria-label="Platform" />
                  <FieldError errors={[errors.social_links?.[index]?.platform]} />
                </div>
                <div className="flex-1">
                  <Input placeholder="https://" {...register(`social_links.${index}.url`)} aria-label="URL" />
                  <FieldError errors={[errors.social_links?.[index]?.url]} />
                </div>
                <Button type="button" variant="ghost" size="icon" onClick={() => socials.remove(index)} aria-label="Remove link">
                  <Trash2Icon />
                </Button>
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" onClick={() => socials.append({ platform: "", url: "" })}>
              <PlusIcon /> Add link
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Competitors</CardTitle>
          <CardDescription>Known competitors guide the Competitor Intelligence agent&apos;s web research.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {competitors.fields.map((field, index) => (
            <div key={field.id} className="grid gap-2 rounded-lg border border-border p-3 md:grid-cols-[1fr_1fr_auto]">
              <div>
                <Input placeholder="Competitor name" {...register(`competitors.${index}.name`)} aria-label="Competitor name" />
                <FieldError errors={[errors.competitors?.[index]?.name]} />
              </div>
              <div>
                <Input placeholder="https://" {...register(`competitors.${index}.website`)} aria-label="Competitor website" />
                <FieldError errors={[errors.competitors?.[index]?.website]} />
              </div>
              <Button type="button" variant="ghost" size="icon" onClick={() => competitors.remove(index)} aria-label="Remove competitor">
                <Trash2Icon />
              </Button>
              <Textarea
                rows={2}
                placeholder="Notes (optional)"
                className="md:col-span-3"
                {...register(`competitors.${index}.notes`)}
                aria-label="Competitor notes"
              />
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => competitors.append({ name: "", website: "", notes: "" })}
          >
            <PlusIcon /> Add competitor
          </Button>
        </CardContent>
      </Card>

      <div className="sticky bottom-0 z-10 -mx-1 flex items-center justify-end gap-3 border-t border-border bg-background/90 px-1 py-3 backdrop-blur">
        {formState.isDirty && <span className="text-sm text-muted-foreground">Unsaved changes</span>}
        <Button type="button" variant="ghost" disabled={!formState.isDirty} onClick={() => form.reset(toForm(brand))}>
          Discard
        </Button>
        <Button type="submit" disabled={!formState.isDirty || update.isPending}>
          {update.isPending ? "Saving…" : "Save profile"}
        </Button>
      </div>
    </form>
  )
}
