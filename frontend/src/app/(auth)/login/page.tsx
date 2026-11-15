import type { Metadata } from "next"
import { Suspense } from "react"

import { LoginForm } from "@/components/auth/login-form"

export const metadata: Metadata = { title: "Sign in" }

/** Only allow redirects within this app (never to another site via ?next=). */
function safeNext(next: string | string[] | undefined): string {
  return typeof next === "string" && next.startsWith("/") && !next.startsWith("//") ? next : "/orgs"
}

async function LoginWithRedirect({ searchParams }: { searchParams: PageProps<"/login">["searchParams"] }) {
  const { next } = await searchParams
  return <LoginForm next={safeNext(next)} />
}

export default function LoginPage({ searchParams }: PageProps<"/login">) {
  // cacheComponents prerenders a static shell. The fallback IS the full form (default
  // redirect), so the prerendered HTML already shows the sign-in card; the version that
  // knows ?next= streams in right after.
  return (
    <Suspense fallback={<LoginForm next="/orgs" />}>
      <LoginWithRedirect searchParams={searchParams} />
    </Suspense>
  )
}
