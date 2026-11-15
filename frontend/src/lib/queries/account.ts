"use client"

import { useMutation, useQueryClient } from "@tanstack/react-query"

import { api, unwrap } from "@/lib/api/client"
import { meQueryKey } from "@/lib/auth/auth-context"

export function useUpdateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (full_name: string) => unwrap(api.PATCH("/api/v1/auth/me", { body: { full_name } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: meQueryKey }),
  })
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      unwrap(api.POST("/api/v1/auth/change-password", { body })),
  })
}
