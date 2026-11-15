"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { errorMessage } from "@/lib/api/errors"
import type { OrganizationWithRole } from "@/lib/api/types"
import { canManage, useUpdateOrganization } from "@/lib/queries/organizations"

const schema = z.object({
  name: z.string().trim().min(1, "Name is required").max(255),
  slug: z
    .string()
    .trim()
    .min(3, "At least 3 characters")
    .max(100)
    .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, "Lowercase letters, numbers and single hyphens"),
})

export function WorkspaceSettings({ org }: { org: OrganizationWithRole }) {
  const update = useUpdateOrganization(org.id)
  const editable = canManage(org.role)
  const form = useForm({ resolver: zodResolver(schema), values: { name: org.name, slug: org.slug } })
  const errors = form.formState.errors

  const onSubmit = form.handleSubmit(async (values) => {
    try {
      await update.mutateAsync(values)
      toast.success("Workspace updated")
    } catch (e) {
      toast.error(errorMessage(e))
    }
  })

  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle>Workspace</CardTitle>
        <CardDescription>
          {editable ? "Visible to every member of this workspace." : "Only admins and owners can edit these."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} noValidate>
          <FieldGroup>
            <Field data-invalid={!!errors.name}>
              <FieldLabel htmlFor="ws-name">Name</FieldLabel>
              <Input id="ws-name" disabled={!editable} {...form.register("name")} />
              <FieldError errors={[errors.name]} />
            </Field>
            <Field data-invalid={!!errors.slug}>
              <FieldLabel htmlFor="ws-slug">Slug</FieldLabel>
              <Input id="ws-slug" disabled={!editable} {...form.register("slug")} />
              <FieldDescription>Unique short name, e.g. northstar-creative.</FieldDescription>
              <FieldError errors={[errors.slug]} />
            </Field>
            {editable && (
              <Button type="submit" disabled={!form.formState.isDirty || update.isPending}>
                Save changes
              </Button>
            )}
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  )
}
