"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, unwrap } from "@/lib/api/client"
import type { BrandDocument, DocumentType } from "@/lib/api/types"

export const documentKeys = {
  list: (brandId: string) => ["brand", brandId, "documents"] as const,
}

const IN_PROGRESS = new Set(["pending", "processing"])

export function useDocuments(brandId: string) {
  return useQuery({
    queryKey: documentKeys.list(brandId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/brands/{brand_id}/documents", {
          params: { path: { brand_id: brandId }, query: { limit: 100 } },
        }),
      ),
    // Poll while the worker is still ingesting something; stop once all are settled.
    refetchInterval: (query) =>
      query.state.data?.items.some((d: BrandDocument) => IN_PROGRESS.has(d.status)) ? 2000 : false,
  })
}

export function useDocumentMutations(brandId: string) {
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: documentKeys.list(brandId) })
  return {
    upload: useMutation({
      mutationFn: ({ file, documentType }: { file: File; documentType: DocumentType }) => {
        const form = new FormData()
        form.append("file", file)
        form.append("document_type", documentType)
        return unwrap(
          api.POST("/api/v1/brands/{brand_id}/documents", {
            params: { path: { brand_id: brandId } },
            // multipart/form-data: hand the FormData to fetch as-is (it sets the boundary).
            body: { file: "", document_type: documentType },
            bodySerializer: () => form,
          }),
        )
      },
      onSuccess: refresh,
    }),
    reindex: useMutation({
      mutationFn: (documentId: string) =>
        unwrap(
          api.POST("/api/v1/documents/{document_id}/reindex", {
            params: { path: { document_id: documentId } },
          }),
        ),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (documentId: string) =>
        unwrap(
          api.DELETE("/api/v1/documents/{document_id}", {
            params: { path: { document_id: documentId } },
          }),
        ),
      onSuccess: refresh,
    }),
  }
}
