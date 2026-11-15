"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api, unwrap } from "@/lib/api/client"
import type { Role } from "@/lib/api/types"
import { meQueryKey, useAuth } from "@/lib/auth/auth-context"

export const orgKeys = {
  dashboard: (orgId: string) => ["org", orgId, "dashboard"] as const,
  members: (orgId: string) => ["org", orgId, "members"] as const,
}

/** The current user's membership (organization + role) for an org id, from /auth/me. */
export function useMembership(orgId: string) {
  const { user } = useAuth()
  return user?.organizations.find((o) => o.id === orgId)
}

export const canManage = (role: Role | undefined) => role === "owner" || role === "admin"

export function useCreateOrganization() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; slug?: string | null }) =>
      unwrap(api.POST("/api/v1/organizations", { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: meQueryKey }),
  })
}

export function useUpdateOrganization(orgId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { name?: string | null; slug?: string | null }) =>
      unwrap(
        api.PATCH("/api/v1/organizations/{organization_id}", {
          params: { path: { organization_id: orgId } },
          body,
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: meQueryKey }),
  })
}

export function useDashboard(orgId: string) {
  return useQuery({
    queryKey: orgKeys.dashboard(orgId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/organizations/{organization_id}/dashboard", {
          params: { path: { organization_id: orgId } },
        }),
      ),
  })
}

export function useMembers(orgId: string) {
  return useQuery({
    queryKey: orgKeys.members(orgId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/organizations/{organization_id}/members", {
          params: { path: { organization_id: orgId } },
        }),
      ).then((page) => page.items),
  })
}

export function useMemberMutations(orgId: string) {
  const queryClient = useQueryClient()
  const refresh = () => queryClient.invalidateQueries({ queryKey: orgKeys.members(orgId) })
  const path = { organization_id: orgId }
  return {
    add: useMutation({
      mutationFn: (body: { email: string; role: Role }) =>
        unwrap(api.POST("/api/v1/organizations/{organization_id}/members", { params: { path }, body })),
      onSuccess: refresh,
    }),
    changeRole: useMutation({
      mutationFn: ({ userId, role }: { userId: string; role: Role }) =>
        unwrap(
          api.PATCH("/api/v1/organizations/{organization_id}/members/{user_id}", {
            params: { path: { ...path, user_id: userId } },
            body: { role },
          }),
        ),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (userId: string) =>
        unwrap(
          api.DELETE("/api/v1/organizations/{organization_id}/members/{user_id}", {
            params: { path: { ...path, user_id: userId } },
          }),
        ),
      onSuccess: async () => {
        await refresh()
        await queryClient.invalidateQueries({ queryKey: meQueryKey }) // in case you left
      },
    }),
  }
}
