"use client"

import { ArrowRightIcon, Building2Icon, LogOutIcon } from "lucide-react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { useEffect, useMemo } from "react"

import { CreateOrgForm } from "@/components/app/create-org-form"
import { Logo } from "@/components/app/logo"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useAuth } from "@/lib/auth/auth-context"
import { titleCase } from "@/lib/format"
import { lastOrg } from "@/lib/workspace"

/** Workspace picker. Returning users jump to their last workspace unless ?choose is set. */
export function OrgPicker() {
  const { user, logout } = useAuth()
  const router = useRouter()
  const choosing = useSearchParams().has("choose")
  const orgs = useMemo(() => user?.organizations ?? [], [user])

  // Return to the workspace used last time (if the user still belongs to it).
  // The read-only demo has exactly one workspace: go straight into it.
  useEffect(() => {
    if (user?.is_demo && orgs[0]) {
      router.replace(`/orgs/${orgs[0].id}/dashboard`)
      return
    }
    const last = lastOrg()
    if (!choosing && last && orgs.some((o) => o.id === last)) {
      router.replace(`/orgs/${last}/dashboard`)
    }
  }, [choosing, orgs, router, user?.is_demo])

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-4 py-10">
      <header className="flex items-center justify-between">
        <Logo />
        <Button variant="ghost" size="sm" onClick={() => logout()}>
          <LogOutIcon /> Sign out
        </Button>
      </header>

      <div className="space-y-1">
        <h1 className="font-heading text-2xl font-semibold">
          Welcome{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}
        </h1>
        <p className="text-sm text-muted-foreground">
          Choose a workspace. Each workspace keeps its brands, documents and campaigns private.
        </p>
      </div>

      {orgs.length > 0 && (
        <div className="grid gap-3">
          {orgs.map((org) => (
            <Link
              key={org.id}
              href={`/orgs/${org.id}/dashboard`}
              className="group flex items-center gap-4 rounded-xl border border-border bg-card px-4 py-3 transition-colors hover:border-primary/40 hover:bg-accent"
            >
              <div className="grid size-10 place-items-center rounded-lg bg-muted">
                <Building2Icon className="size-5 text-muted-foreground" aria-hidden />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{org.name}</p>
                <p className="truncate text-xs text-muted-foreground">{org.slug}</p>
              </div>
              <Badge variant="secondary">{titleCase(org.role)}</Badge>
              <ArrowRightIcon className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
            </Link>
          ))}
        </div>
      )}

      {!user?.is_demo && (
        <Card>
          <CardHeader>
            <CardTitle>{orgs.length ? "Create another workspace" : "Create your first workspace"}</CardTitle>
            <CardDescription>You will be its owner and can invite your team later.</CardDescription>
          </CardHeader>
          <CardContent>
            <CreateOrgForm />
          </CardContent>
        </Card>
      )}
    </main>
  )
}
