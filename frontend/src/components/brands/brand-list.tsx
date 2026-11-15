"use client"

import { BriefcaseIcon, PlusIcon, SearchIcon } from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useDeferredValue, useState } from "react"

import { EmptyState } from "@/components/app/empty-state"
import { PageHeader } from "@/components/app/page-header"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { errorMessage } from "@/lib/api/errors"
import { formatRelative } from "@/lib/format"
import { useBrands } from "@/lib/queries/brands"

import { CreateBrandDialog } from "./create-brand-dialog"

export function BrandList({ orgId }: { orgId: string }) {
  const router = useRouter()
  const pathname = usePathname()
  const creating = useSearchParams().has("new")
  const [search, setSearch] = useState("")
  const deferredSearch = useDeferredValue(search.trim()) // don't query on every keystroke
  const { data, isPending, error } = useBrands(orgId, deferredSearch)

  const setCreating = (open: boolean) => router.replace(open ? `${pathname}?new=1` : pathname)

  return (
    <>
      <PageHeader
        title="Brands"
        description="Each brand has its own profile and private knowledge base that the agents research."
        actions={
          <Button onClick={() => setCreating(true)}>
            <PlusIcon /> New brand
          </Button>
        }
      />

      <div className="relative max-w-sm">
        <SearchIcon className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search brands…"
          className="pl-9"
          aria-label="Search brands"
        />
      </div>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{errorMessage(error)}</AlertDescription>
        </Alert>
      ) : isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-32 rounded-xl" />
          ))}
        </div>
      ) : data.items.length === 0 ? (
        <EmptyState
          icon={BriefcaseIcon}
          title={deferredSearch ? "No brands match your search" : "No brands yet"}
          description={
            deferredSearch ? undefined : "Create your first brand to start building its knowledge base."
          }
          action={
            !deferredSearch && (
              <Button onClick={() => setCreating(true)}>
                <PlusIcon /> New brand
              </Button>
            )
          }
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((brand) => (
            <Link
              key={brand.id}
              href={`/orgs/${orgId}/brands/${brand.id}`}
              className="group flex flex-col gap-3 rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/40 hover:bg-accent"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="font-heading text-lg font-semibold group-hover:text-primary">{brand.name}</p>
                {brand.industry && <Badge variant="secondary">{brand.industry}</Badge>}
              </div>
              <p className="line-clamp-2 min-h-10 text-sm text-muted-foreground">
                {brand.description || "No description yet."}
              </p>
              <p className="mt-auto text-xs text-muted-foreground">Updated {formatRelative(brand.updated_at)}</p>
            </Link>
          ))}
        </div>
      )}

      <CreateBrandDialog orgId={orgId} open={creating} onOpenChange={setCreating} />
    </>
  )
}
