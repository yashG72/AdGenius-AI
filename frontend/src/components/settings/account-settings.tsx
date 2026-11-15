"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { errorMessage } from "@/lib/api/errors"
import { useAuth } from "@/lib/auth/auth-context"
import { useChangePassword, useUpdateProfile } from "@/lib/queries/account"

const profileSchema = z.object({ full_name: z.string().trim().min(1, "Enter your name").max(255) })
const passwordSchema = z
  .object({
    current_password: z.string().min(1, "Enter your current password"),
    new_password: z.string().min(8, "At least 8 characters").max(128),
    confirm: z.string(),
  })
  .refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Passwords don't match" })

export function AccountSettings() {
  const { user, logout } = useAuth()
  const updateProfile = useUpdateProfile()
  const changePassword = useChangePassword()

  const profile = useForm({
    resolver: zodResolver(profileSchema),
    values: { full_name: user?.full_name ?? "" },
  })
  const password = useForm({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current_password: "", new_password: "", confirm: "" },
  })

  const saveProfile = profile.handleSubmit(async ({ full_name }) => {
    try {
      await updateProfile.mutateAsync(full_name)
      toast.success("Profile updated")
    } catch (e) {
      toast.error(errorMessage(e))
    }
  })

  const savePassword = password.handleSubmit(async ({ current_password, new_password }) => {
    try {
      await changePassword.mutateAsync({ current_password, new_password })
      toast.success("Password changed — please sign in again")
      await logout() // the backend revoked every session, including this one
    } catch (e) {
      toast.error(errorMessage(e))
    }
  })

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>{user?.email}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={saveProfile} noValidate>
            <FieldGroup>
              <Field data-invalid={!!profile.formState.errors.full_name}>
                <FieldLabel htmlFor="full_name">Full name</FieldLabel>
                <Input id="full_name" {...profile.register("full_name")} />
                <FieldError errors={[profile.formState.errors.full_name]} />
              </Field>
              <Button type="submit" disabled={!profile.formState.isDirty || updateProfile.isPending}>
                Save
              </Button>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Change password</CardTitle>
          <CardDescription>Signs you out everywhere, including this browser.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={savePassword} noValidate>
            <FieldGroup>
              <Field data-invalid={!!password.formState.errors.current_password}>
                <FieldLabel htmlFor="current_password">Current password</FieldLabel>
                <Input id="current_password" type="password" autoComplete="current-password" {...password.register("current_password")} />
                <FieldError errors={[password.formState.errors.current_password]} />
              </Field>
              <Field data-invalid={!!password.formState.errors.new_password}>
                <FieldLabel htmlFor="new_password">New password</FieldLabel>
                <Input id="new_password" type="password" autoComplete="new-password" {...password.register("new_password")} />
                <FieldError errors={[password.formState.errors.new_password]} />
              </Field>
              <Field data-invalid={!!password.formState.errors.confirm}>
                <FieldLabel htmlFor="confirm">Confirm new password</FieldLabel>
                <Input id="confirm" type="password" autoComplete="new-password" {...password.register("confirm")} />
                <FieldError errors={[password.formState.errors.confirm]} />
              </Field>
              <Button type="submit" variant="secondary" disabled={changePassword.isPending}>
                Change password
              </Button>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
