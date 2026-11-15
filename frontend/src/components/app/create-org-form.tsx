"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useRouter } from "next/navigation"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { errorMessage } from "@/lib/api/errors"
import { useCreateOrganization } from "@/lib/queries/organizations"

const schema = z.object({ name: z.string().trim().min(1, "Name your workspace").max(255) })

export function CreateOrgForm({ onCreated }: { onCreated?: () => void }) {
  const router = useRouter()
  const create = useCreateOrganization()
  const form = useForm({ resolver: zodResolver(schema), defaultValues: { name: "" } })

  const onSubmit = form.handleSubmit(async ({ name }) => {
    try {
      const org = await create.mutateAsync({ name })
      toast.success(`Workspace “${org.name}” created`)
      onCreated?.()
      router.push(`/orgs/${org.id}/dashboard`)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  })

  return (
    <form onSubmit={onSubmit} noValidate>
      <FieldGroup>
        <Field data-invalid={!!form.formState.errors.name}>
          <FieldLabel htmlFor="org-name">Workspace name</FieldLabel>
          <Input id="org-name" placeholder="e.g. Northstar Creative" {...form.register("name")} />
          <FieldError errors={[form.formState.errors.name]} />
        </Field>
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? "Creating…" : "Create workspace"}
        </Button>
      </FieldGroup>
    </form>
  )
}
