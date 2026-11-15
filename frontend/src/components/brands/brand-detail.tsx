"use client"

import { ArrowLeftIcon, Trash2Icon } from "lucide-react"
import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"

import { ConfirmDialog } from "@/components/app/confirm-dialog"
import { PageHeader } from "@/components/app/page-header"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { errorMessage } from "@/lib/api/errors"
import { useBrand, useDeleteBrand } from "@/lib/queries/brands"
import { canManage, useMembership } from "@/lib/queries/organizations"

import { BrandProfileForm } from "./brand-profile-form"
import { DocumentsPanel } from "./documents-panel"

export function BrandDetail({ orgId, brandId }: { orgId: string; brandId: string }) {
  const router = useRouter()
  const pathname = usePathname()
  const tab = useSearchParams().get("tab") === "documents" ? "documents" : "profile"
  const { data: brand, isPending, error } = useBrand(brandId)
  const remove = useDeleteBrand(orgId)
  const isAdmin = canManage(useMembership(orgId)?.role)

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage(error)}</AlertDescription>
      </Alert>
    )
  }
  if (isPending) return <Skeleton className="h-96 rounded-xl" />

  return (
    <>
      <Link
        href={`/orgs/${orgId}/brands`}
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeftIcon className="size-4" /> All brands
      </Link>
      <PageHeader title={brand.name} description={brand.description ?? undefined} />

      <Tabs
        value={tab}
        onValueChange={(value) => router.replace(value === "documents" ? `${pathname}?tab=documents` : pathname)}
      >
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="documents">Knowledge base</TabsTrigger>
        </TabsList>
        <TabsContent value="profile" className="mt-6 space-y-6">
          <BrandProfileForm orgId={orgId} brand={brand} />
          {isAdmin && (
            <Card className="border-destructive/40">
              <CardHeader>
                <CardTitle>Danger zone</CardTitle>
                <CardDescription>
                  Deleting removes the brand, its documents and their search index from this workspace.
                  Existing campaign history is kept.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ConfirmDialog
                  title={`Delete ${brand.name}?`}
                  description="This cannot be undone from the app."
                  confirmLabel="Delete brand"
                  onConfirm={() =>
                    remove.mutate(brand.id, {
                      onSuccess: () => {
                        toast.success(`${brand.name} deleted`)
                        router.replace(`/orgs/${orgId}/brands`)
                      },
                      onError: (e) => toast.error(errorMessage(e)),
                    })
                  }
                  trigger={
                    <Button variant="destructive">
                      <Trash2Icon /> Delete brand
                    </Button>
                  }
                />
              </CardContent>
            </Card>
          )}
        </TabsContent>
        <TabsContent value="documents" className="mt-6">
          <DocumentsPanel brandId={brand.id} canDelete={isAdmin} />
        </TabsContent>
      </Tabs>
    </>
  )
}
