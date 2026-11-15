"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, unwrap } from "@/lib/api/client"
import { ApiError } from "@/lib/api/errors"
import type {
  BriefFields,
  CampaignCreate,
  OutputType,
  RunDetail,
  Script,
  Storyboard,
} from "@/lib/api/types"
import { ACTIVE_STATUSES } from "@/lib/api/types"
import { getAccessToken } from "@/lib/auth/token-store"
import { API_URL } from "@/lib/config"

export const campaignKeys = {
  list: (orgId: string, brandId?: string) => ["org", orgId, "campaigns", brandId ?? "all"] as const,
  all: (orgId: string) => ["org", orgId, "campaigns"] as const,
  detail: (campaignId: string) => ["campaign", campaignId] as const,
  runs: (campaignId: string) => ["campaign", campaignId, "runs"] as const,
  run: (runId: string) => ["run", runId] as const,
  output: (runId: string, type: OutputType, version?: number) =>
    ["run", runId, "output", type, version ?? "latest"] as const,
  evaluation: (runId: string) => ["run", runId, "evaluation-summary"] as const,
}

// ---------- campaigns ----------

export function useCampaigns(orgId: string, brandId?: string) {
  return useQuery({
    queryKey: campaignKeys.list(orgId, brandId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/campaigns", {
          params: { query: { organization_id: orgId, brand_id: brandId, limit: 100 } },
        }),
      ),
  })
}

export function useCampaign(campaignId: string) {
  return useQuery({
    queryKey: campaignKeys.detail(campaignId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/campaigns/{campaign_id}", { params: { path: { campaign_id: campaignId } } })),
  })
}

export function useCreateCampaign(orgId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: CampaignCreate) => unwrap(api.POST("/api/v1/campaigns", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: campaignKeys.all(orgId) }),
  })
}

export function useUpdateCampaign(orgId: string, campaignId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { name?: string; brief?: BriefFields }) =>
      unwrap(
        api.PATCH("/api/v1/campaigns/{campaign_id}", { params: { path: { campaign_id: campaignId } }, body }),
      ),
    onSuccess: (campaign) => {
      queryClient.setQueryData(campaignKeys.detail(campaignId), campaign)
      return queryClient.invalidateQueries({ queryKey: campaignKeys.all(orgId) })
    },
  })
}

// ---------- runs ----------

export function useRuns(campaignId: string) {
  return useQuery({
    queryKey: campaignKeys.runs(campaignId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/campaigns/{campaign_id}/runs", { params: { path: { campaign_id: campaignId } } }),
      ).then((r) => r.items),
  })
}

export function useRun(runId: string) {
  return useQuery({
    queryKey: campaignKeys.run(runId),
    queryFn: () =>
      unwrap(api.GET("/api/v1/campaign-runs/{run_id}", { params: { path: { run_id: runId } } })),
    // The live event stream triggers refreshes; this slow poll is only a safety net.
    refetchInterval: (query) =>
      query.state.data && ACTIVE_STATUSES.includes((query.state.data as RunDetail).status) ? 10_000 : false,
  })
}

/** Start a new run (generate) or a new version of an existing run (regenerate). */
export function useStartRun(orgId: string, campaignId: string) {
  const queryClient = useQueryClient()
  const refresh = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: campaignKeys.runs(campaignId) }),
      queryClient.invalidateQueries({ queryKey: campaignKeys.detail(campaignId) }),
      queryClient.invalidateQueries({ queryKey: campaignKeys.all(orgId) }),
    ])
  return {
    generate: useMutation({
      mutationFn: () =>
        unwrap(
          api.POST("/api/v1/campaigns/{campaign_id}/generate", { params: { path: { campaign_id: campaignId } } }),
        ),
      onSuccess: refresh,
    }),
    regenerate: useMutation({
      mutationFn: (runId: string) =>
        unwrap(api.POST("/api/v1/campaign-runs/{run_id}/regenerate", { params: { path: { run_id: runId } } })),
      onSuccess: refresh,
    }),
    retry: useMutation({
      mutationFn: (runId: string) =>
        unwrap(api.POST("/api/v1/campaign-runs/{run_id}/retry", { params: { path: { run_id: runId } } })),
      onSuccess: (run) =>
        Promise.all([refresh(), queryClient.invalidateQueries({ queryKey: campaignKeys.run(run.id) })]),
    }),
  }
}

// ---------- approvals ----------

export function useDecision(runId: string) {
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: campaignKeys.run(runId) })
  return {
    approve: useMutation({
      mutationFn: ({ approvalId, conceptId, feedback }: { approvalId: string; conceptId: string; feedback?: string }) =>
        unwrap(
          api.POST("/api/v1/approvals/{approval_id}/approve", {
            params: { path: { approval_id: approvalId } },
            body: { concept_id: conceptId, feedback: feedback || null },
          }),
        ),
      onSuccess: refresh,
    }),
    reject: useMutation({
      mutationFn: ({ approvalId, feedback }: { approvalId: string; feedback: string }) =>
        unwrap(
          api.POST("/api/v1/approvals/{approval_id}/reject", {
            params: { path: { approval_id: approvalId } },
            body: { feedback },
          }),
        ),
      onSuccess: refresh,
    }),
  }
}

// ---------- outputs ----------

export function useOutput(runId: string, type: OutputType, options: { version?: number; enabled?: boolean } = {}) {
  return useQuery({
    queryKey: campaignKeys.output(runId, type, options.version),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/campaign-runs/{run_id}/outputs/{output_type}", {
          params: { path: { run_id: runId, output_type: type }, query: { version: options.version } },
        }),
      ),
    enabled: options.enabled ?? true,
  })
}

export function useSaveOutput(runId: string) {
  const queryClient = useQueryClient()
  const refresh = (type: OutputType) =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["run", runId, "output", type] }),
      queryClient.invalidateQueries({ queryKey: campaignKeys.run(runId) }),
    ])
  return {
    script: useMutation({
      mutationFn: (body: Script) =>
        unwrap(api.PUT("/api/v1/campaign-runs/{run_id}/script", { params: { path: { run_id: runId } }, body })),
      onSuccess: () => refresh("script"),
    }),
    storyboard: useMutation({
      mutationFn: (body: Storyboard) =>
        unwrap(api.PUT("/api/v1/campaign-runs/{run_id}/storyboard", { params: { path: { run_id: runId } }, body })),
      onSuccess: () => refresh("storyboard"),
    }),
  }
}

export function useEvaluationSummary(runId: string, enabled: boolean) {
  return useQuery({
    queryKey: campaignKeys.evaluation(runId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/campaign-runs/{run_id}/evaluation-summary", { params: { path: { run_id: runId } } }),
      ),
    enabled,
  })
}

/** Download the PDF with the auth header (a plain <a href> can't send one). */
export async function downloadRunPdf(runId: string): Promise<void> {
  const token = await getAccessToken()
  const response = await fetch(`${API_URL}/api/v1/campaign-runs/${runId}/export.pdf`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) throw ApiError.from(response.status, await response.json().catch(() => ({})))
  const filename =
    /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "")?.[1] ?? "campaign.pdf"
  const url = URL.createObjectURL(await response.blob())
  const link = Object.assign(document.createElement("a"), { href: url, download: filename })
  link.click()
  URL.revokeObjectURL(url)
}
