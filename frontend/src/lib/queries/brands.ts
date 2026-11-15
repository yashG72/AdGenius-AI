"use client"

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, unwrap } from "@/lib/api/client"
import type { BrandCreate, BrandUpdate } from "@/lib/api/types"

export const brandKeys = {
  list: (orgId: string, search: string) => ["org", orgId, "brands", search] as const,
  all: (orgId: string) => ["org", orgId, "brands"] as const,
  detail: (brandId: string) => ["brand", brandId] as const,
}

export function useBrands(orgId: string, search = "") {
  return useQuery({
    queryKey: brandKeys.list(orgId, search),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/brands", {
          params: { query: { organization_id: orgId, search: search || undefined, limit: 100 } },
        }),
      ),
    placeholderData: keepPreviousData, // no flicker while typing a search
  })
}

export function useBrand(brandId: string) {
  return useQuery({
    queryKey: brandKeys.detail(brandId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/brands/{brand_id}", { params: { path: { brand_id: brandId } } })),
    enabled: !!brandId, // e.g. while the campaign that names the brand is still loading
  })
}

export function useCreateBrand(orgId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: BrandCreate) => unwrap(api.POST("/api/v1/brands", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: brandKeys.all(orgId) }),
  })
}

export function useUpdateBrand(orgId: string, brandId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: BrandUpdate) =>
      unwrap(api.PATCH("/api/v1/brands/{brand_id}", { params: { path: { brand_id: brandId } }, body })),
    onSuccess: (brand) => {
      queryClient.setQueryData(brandKeys.detail(brandId), brand)
      return queryClient.invalidateQueries({ queryKey: brandKeys.all(orgId) })
    },
  })
}

export function useDeleteBrand(orgId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (brandId: string) =>
      unwrap(api.DELETE("/api/v1/brands/{brand_id}", { params: { path: { brand_id: brandId } } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: brandKeys.all(orgId) }),
  })
}
