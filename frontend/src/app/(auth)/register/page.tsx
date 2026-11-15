"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { errorMessage } from "@/lib/api/errors"
import { useAuth } from "@/lib/auth/auth-context"

// Mirrors the backend rules (8-128 char passwords) so users get instant feedback.
const schema = z
  .object({
    full_name: z.string().trim().min(1, "Enter your name").max(255),
    email: z.email("Enter a valid email"),
    password: z.string().min(8, "At least 8 characters").max(128),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords don't match" })
type Values = z.infer<typeof schema>

export default function RegisterPage() {
  const { register } = useAuth()
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { full_name: "", email: "", password: "", confirm: "" },
  })
  const errors = form.formState.errors

  const onSubmit = form.handleSubmit(async ({ full_name, email, password }) => {
    setError(null)
    try {
      await register({ full_name, email, password })
      router.replace("/orgs")
    } catch (e) {
      setError(errorMessage(e))
    }
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create your account</CardTitle>
        <CardDescription>Then set up a workspace for your agency or team.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} noValidate>
          <FieldGroup>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Field data-invalid={!!errors.full_name}>
              <FieldLabel htmlFor="full_name">Full name</FieldLabel>
              <Input id="full_name" autoComplete="name" {...form.register("full_name")} />
              <FieldError errors={[errors.full_name]} />
            </Field>
            <Field data-invalid={!!errors.email}>
              <FieldLabel htmlFor="email">Work email</FieldLabel>
              <Input id="email" type="email" autoComplete="email" {...form.register("email")} />
              <FieldError errors={[errors.email]} />
            </Field>
            <Field data-invalid={!!errors.password}>
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <Input id="password" type="password" autoComplete="new-password" {...form.register("password")} />
              <FieldDescription>At least 8 characters.</FieldDescription>
              <FieldError errors={[errors.password]} />
            </Field>
            <Field data-invalid={!!errors.confirm}>
              <FieldLabel htmlFor="confirm">Confirm password</FieldLabel>
              <Input id="confirm" type="password" autoComplete="new-password" {...form.register("confirm")} />
              <FieldError errors={[errors.confirm]} />
            </Field>
            <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? "Creating account…" : "Create account"}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              Already have an account?{" "}
              <Link href="/login" className="text-primary underline-offset-4 hover:underline">
                Sign in
              </Link>
            </p>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  )
}
