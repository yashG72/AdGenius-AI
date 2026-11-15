"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useRouter } from "next/navigation"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { errorMessage } from "@/lib/api/errors"
import { useCreateBrand } from "@/lib/queries/brands"

const schema = z.object({
  name: z.string().trim().min(1, "Give the brand a name").max(255),
  industry: z.string().trim().max(100),
  description: z.string().trim().max(10_000),
})
type Values = z.infer<typeof schema>

export function CreateBrandDialog({
  orgId,
  open,
  onOpenChange,
}: {
  orgId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const router = useRouter()
  const create = useCreateBrand(orgId)
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", industry: "", description: "" },
  })
  const errors = form.formState.errors

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      const brand = await create.mutateAsync({
        organization_id: orgId,
        name: values.name,
        industry: values.industry || null,
        description: values.description || null,
      })
      toast.success(`${brand.name} created — now add its profile and documents`)
      onOpenChange(false)
      form.reset()
      router.push(`/orgs/${orgId}/brands/${brand.id}`)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={onSubmit} noValidate>
          <DialogHeader>
            <DialogTitle>New brand</DialogTitle>
            <DialogDescription>
              Start with the basics; you can fill in voice, audience and restrictions next.
            </DialogDescription>
          </DialogHeader>
          <FieldGroup className="py-4">
            <Field data-invalid={!!errors.name}>
              <FieldLabel htmlFor="brand-name">Brand name</FieldLabel>
              <Input id="brand-name" autoFocus {...form.register("name")} />
              <FieldError errors={[errors.name]} />
            </Field>
            <Field>
              <FieldLabel htmlFor="brand-industry">Industry</FieldLabel>
              <Input id="brand-industry" placeholder="e.g. Beverages" {...form.register("industry")} />
            </Field>
            <Field>
              <FieldLabel htmlFor="brand-description">Short description</FieldLabel>
              <Textarea id="brand-description" rows={3} {...form.register("description")} />
            </Field>
          </FieldGroup>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create brand"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
