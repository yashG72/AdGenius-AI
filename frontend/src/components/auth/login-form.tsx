"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { errorMessage } from "@/lib/api/errors"
import { useAuth } from "@/lib/auth/auth-context"

const schema = z.object({
  email: z.email("Enter a valid email"),
  password: z.string().min(1, "Enter your password"),
})
type Values = z.infer<typeof schema>

/** The `next` redirect is already validated by the page (same-app paths only). */
export function LoginForm({ next }: { next: string }) {
  const { login, status } = useAuth()
  const router = useRouter()
  const [error, setError] = useState<string | null>(null)
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } })

  useEffect(() => {
    if (status === "authenticated") router.replace(next)
  }, [status, next, router])

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null)
    try {
      await login(values.email, values.password)
    } catch (e) {
      setError(errorMessage(e))
    }
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>Welcome back. Sign in to your workspace.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} noValidate>
          <FieldGroup>
            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}
            <Field data-invalid={!!form.formState.errors.email}>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input id="email" type="email" autoComplete="email" {...form.register("email")} />
              <FieldError errors={[form.formState.errors.email]} />
            </Field>
            <Field data-invalid={!!form.formState.errors.password}>
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                {...form.register("password")}
              />
              <FieldError errors={[form.formState.errors.password]} />
            </Field>
            <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
              {form.formState.isSubmitting ? "Signing in…" : "Sign in"}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              New here?{" "}
              <Link href="/register" className="text-primary underline-offset-4 hover:underline">
                Create an account
              </Link>
            </p>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  )
}
